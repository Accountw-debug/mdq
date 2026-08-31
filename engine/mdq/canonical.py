"""Kanonisches Mapping: ``staged_<TABELLE>`` -> die Tabellen aus ``logic/schema/canonical.sql``.

Die dritte Stufe der Pipeline ``raw -> staged -> canonical -> findings`` (Regel 3). Hier
bekommen die Spalten ihre kanonischen Namen, die Schluessel ihr Rollenpraefix und die
Nebentabellen ihre Zeilenform. Gerechnet wird nichts mehr: ``amount_signed_local`` und
``reference_norm`` kommen unveraendert aus dem Staging (D-009, D-065), ``value_norm`` und
``iban_norm`` ebenso - eine zweite Berechnung waere eine zweite Wahrheit.

Die Feldlisten stehen ausschliesslich in ``logic/mappings/sap_ecc.yaml``; dieses Modul
erzeugt daraus je Quelltabelle ein ``INSERT ... SELECT`` (D-072). Welche Quellspalte
Pflicht ist, leitet es aus ``canonical.sql`` ab: jede Zielspalte ``NOT NULL`` ohne
``DEFAULT`` macht die zuliefernde Quellspalte zur Pflicht. Fehlt eine solche Spalte,
bricht die Stufe ab und nennt Tabelle und Spalte - anders als beim Staging, wo eine
fehlende Spalte nur ein Hinweis ist: eine Tabelle ohne Pflichtspalte laesst sich nicht
bilden, und ein halbes ``fi_item`` waere ein stumm verworfener Teil des Mandanten
(Regel 4, D-077).

Was nicht gebildet werden kann, wird ausgewiesen, nicht verschwiegen:

* Zeile ohne Stammsatz -> ``reject`` (Stufe ``canonical``) mit dem ``bp_key`` im Grund.
* Pflichtfeld leer -> ``reject`` mit kanonischem Feldnamen und Quellspalte.
* Doppelter Primaerschluessel -> ``reject`` fuer **beide** Zeilen; keine gewinnt still.
* Ausserhalb des Scopes -> kein Reject (D-075), aber eine Zeile im Run-Report.

``name_norm``, ``city_norm`` und ``street_norm`` bleiben in diesem Sprint NULL: ihre
Normalisierung definiert die Dubletten-Spec in Sprint 4, und keine der Regeln dieses
Sprints liest sie. Der Run-Report sagt das ausdruecklich an (D-079).
"""

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import duckdb
from schwifty import IBAN
from schwifty.exceptions import SchwiftyException

from mdq import CANONICAL_SCHEMA
from mdq.dictionaries import DictionaryError, load_vat_patterns
from mdq.loader import ROW_NO_COLUMN
from mdq.mapping import Mapping, TableMapping

#: Stufe, unter der Rejects dieses Schritts in ``reject`` stehen
STAGE = "canonical"

#: Rollenpraefix des ``bp_key`` (D-009, Mapping-Abschnitt ``derivations``)
ROLE_PREFIX = {"CUSTOMER": "C:", "VENDOR": "V:"}

#: ``--side`` -> die Rollen, die der Lauf aufnimmt
SIDES = {"ar": ("CUSTOMER",), "ap": ("VENDOR",), "both": ("CUSTOMER", "VENDOR")}

#: Zielspalten, die einen Partnerschluessel tragen und deshalb das Rollenpraefix bekommen
PREFIXED_TARGETS = ("alt_payer_key", "bp_key", "dunning_recipient_key", "partner_bp_key")

#: Normalisierte Namens- und Adressfelder; ihre Definition kommt mit der Dubletten-Spec
DEFERRED_TO_SPRINT_4 = ("city_norm", "name_norm", "street_norm")

#: Reihenfolge des Aufbaus: Stammsatz vor allem, was auf ihn verweist (Regel 9).
#: ``company_code`` steht ganz vorn: es traegt die Hauswaehrung, in der jeder Betrag
#: der spaeteren Tabellen steht (D-030).
TARGET_ORDER = (
    "company_code",
    "business_partner",
    "bp_tax_id",
    "bp_company_code",
    "bp_bank_account",
    "bp_partner_function",
    "bp_dunning",
    "payment_terms",
    "fi_item",
)

#: Praefix der Nebenziele im Mapping (``STCD1: tax_id.TAX1``)
TAX_ID_PREFIX = "tax_id."

#: Sprachschluessel fuer die Zahlungsbedingungstexte, in der Reihenfolge ihrer Bevorzugung.
#: SAP fuehrt Deutsch als ``D``, nicht als ``DE`` (D-074).
LANGUAGE_ORDER = ("D", "E")

#: Kanonische Pflichtspalten ohne eigene Zuordnung im Mapping: was ihre Ableitung braucht,
#: benannt in kanonischen Feldern. Ein leeres Tupel heisst: die Spalte kommt aus dem
#: Mapping selbst (``role``, ``is_open``) und haengt an keiner Exportspalte.
DERIVED_REQUIREMENTS = {
    "business_partner": {"bp_key": ("source_id",), "role": ()},
    "fi_item": {
        "item_key": ("company_code", "fiscal_year", "document_no", "line_item"),
        "amount_signed_local": ("amount_local", "debit_credit"),
        "is_open": (),
    },
}

#: Primaerschluessel der Zieltabellen – hier waere ein Duplikat sonst ein nackter
#: Constraint-Fehler von DuckDB statt einer Meldung mit Grund (Regel 4)
PRIMARY_KEYS = {
    "company_code": ("company_code",),
    "business_partner": ("bp_key",),
    "bp_company_code": ("bp_key", "company_code"),
    "fi_item": ("item_key",),
}

#: Spalte mit dem Grund, an dem eine Zeile scheitert (NULL = Zeile ist brauchbar)
REASON_COLUMN = "__reject_reason"

_CREATE_RE = re.compile(r"^CREATE TABLE IF NOT EXISTS (\w+)\s*\(", re.IGNORECASE)
_PRIMARY_KEY_RE = re.compile(r"^PRIMARY KEY\s*\(([^)]*)\)", re.IGNORECASE)
_DEFAULT_RE = re.compile(r"\bDEFAULT\s+(\S+)", re.IGNORECASE)
_CONSTRAINTS = ("PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "CONSTRAINT")


class CanonicalError(ValueError):
    """Die Stufe ``canonical`` kann eine Tabelle nicht bilden – der Lauf bricht ab."""


# --- Das kanonische Schema als Datenstruktur -------------------------------------------


@dataclass(frozen=True)
class ColumnDef:
    """Eine Spalte aus ``canonical.sql``."""

    name: str
    not_null: bool
    #: der ``DEFAULT``-Ausdruck im Wortlaut des Schemas, ``None`` ohne Vorgabe
    default: str | None = None

    @property
    def has_default(self) -> bool:
        return self.default is not None

    @property
    def required(self) -> bool:
        """Pflicht: ``NOT NULL`` und kein ``DEFAULT``, der die Luecke fuellen wuerde."""
        return self.not_null and not self.has_default


def parse_schema(path: Path = CANONICAL_SCHEMA) -> dict[str, tuple[ColumnDef, ...]]:
    """Liest die Spalten je Tabelle aus ``canonical.sql``.

    Gelesen wird die Datei, nicht eine zweite Liste im Code: welche Spalte Pflicht ist,
    steht im Schema, und beide Orte auseinanderlaufen zu lassen ist genau der Fehler,
    den die Pflichtpruefung verhindern soll.
    """
    tables: dict[str, list[ColumnDef]] = {}
    current: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("--", 1)[0].strip()
        if not line:
            continue
        start = _CREATE_RE.match(line)
        if start:
            current = start.group(1)
            tables[current] = []
            continue
        if current is None:
            continue
        if line.startswith(");"):
            current = None
            continue
        entry = line.rstrip(",").strip()
        if not entry:
            continue
        head = entry.split()[0].upper()
        if head in _CONSTRAINTS:
            key = _PRIMARY_KEY_RE.match(entry)
            if key:
                named = {name.strip() for name in key.group(1).split(",")}
                tables[current] = [
                    ColumnDef(column.name, column.not_null or column.name in named,
                              column.default)
                    for column in tables[current]
                ]
            continue
        upper = entry.upper()
        default = _DEFAULT_RE.search(entry)
        tables[current].append(
            ColumnDef(
                name=entry.split()[0],
                not_null="NOT NULL" in upper or "PRIMARY KEY" in upper,
                default=default.group(1) if default else None,
            )
        )
    return {name: tuple(columns) for name, columns in tables.items()}


# --- Scope und Ergebnis ----------------------------------------------------------------


@dataclass(frozen=True)
class Scope:
    """Was ein Lauf aufnimmt: Buchungskreise, Seite, Postenfenster.

    Leere ``company_codes`` heissen: alle. Das Postenfenster bleibt in diesem Sprint
    ohne CLI-Parameter; es kommt mit ``run_meta.scope`` in Aufgabe 4.
    """

    company_codes: tuple[str, ...] = ()
    side: str = "both"
    item_window_from: date | None = None
    item_window_to: date | None = None

    def __post_init__(self) -> None:
        if self.side not in SIDES:
            raise CanonicalError(
                f"unbekannte Seite {self.side!r}; erlaubt sind {sorted(SIDES)}."
            )

    @property
    def roles(self) -> tuple[str, ...]:
        return SIDES[self.side]

    def to_dict(self) -> dict:
        """Der Scope als JSON – so steht er in ``run.json`` und in ``run_meta.scope``.

        Leere ``company_codes`` heissen "alle": die Liste beschreibt den **Filter**, nicht
        den Inhalt des Laufs. Welche Buchungskreise wirklich enthalten sind, sagt
        ``run.json`` unter ``company_codes`` (D-095).
        """
        return {
            "company_codes": list(self.company_codes),
            "side": self.side,
            "item_window_from": _iso(self.item_window_from),
            "item_window_to": _iso(self.item_window_to),
        }

    def describe(self) -> str:
        """Einzeiler fuer den Run-Report – der Scope muss sichtbar sein, nicht erraten."""
        codes = ", ".join(self.company_codes) if self.company_codes else "alle"
        window = "alle"
        if self.item_window_from or self.item_window_to:
            window = f"{self.item_window_from or '…'} bis {self.item_window_to or '…'}"
        return f"Buchungskreise: {codes} · Seite: {self.side} · Postenfenster: {window}"


@dataclass(frozen=True)
class TableResult:
    """Ergebnis einer kanonischen Zieltabelle."""

    table: str
    rows: int
    rejected: int
    out_of_scope: int
    sources: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "table": self.table,
            "rows": self.rows,
            "rejected": self.rejected,
            "out_of_scope": self.out_of_scope,
            "sources": list(self.sources),
        }


@dataclass(frozen=True)
class CanonicalResult:
    """Ergebnis der Stufe ``canonical`` – Grundlage des Report-Blocks."""

    scope: Scope
    tables: tuple[TableResult, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)
    #: tatsaechlich geliefertes Buchungsdatum, nur berichtet – kein Filter (Aufgabe 4)
    posting_date_from: date | None = None
    posting_date_to: date | None = None

    @property
    def out_of_scope_partners(self) -> int:
        return sum(t.out_of_scope for t in self.tables if t.table == "business_partner")

    @property
    def out_of_scope_items(self) -> int:
        return sum(t.out_of_scope for t in self.tables if t.table == "fi_item")

    @property
    def rows_total(self) -> int:
        return sum(t.rows for t in self.tables)

    @property
    def rejected_total(self) -> int:
        return sum(t.rejected for t in self.tables)

    def to_dict(self) -> dict:
        return {
            "scope": {
                "company_codes": list(self.scope.company_codes),
                "side": self.scope.side,
                "item_window_from": _iso(self.scope.item_window_from),
                "item_window_to": _iso(self.scope.item_window_to),
            },
            "posting_date_from": _iso(self.posting_date_from),
            "posting_date_to": _iso(self.posting_date_to),
            "out_of_scope_partners": self.out_of_scope_partners,
            "out_of_scope_items": self.out_of_scope_items,
            "tables": [table.to_dict() for table in self.tables],
            "warnings": list(self.warnings),
        }


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


# --- Vom Mapping zur Spalte ------------------------------------------------------------


def _inverse(table: TableMapping) -> dict[str, str]:
    """Kanonisches Feld -> SAP-Spalte; die Nebenziele ``tax_id.*`` bleiben aussen vor."""
    return {
        target: source
        for source, target in table.fields.items()
        if not target.startswith(TAX_ID_PREFIX) and "." not in target
    }


def _is_main_target(table: TableMapping) -> bool:
    """Wahr, wenn die Tabelle eine ganze Zieltabelle fuellt und nicht nur ein Feld."""
    return table.is_staged and table.target is not None and "." not in table.target


def required_sources(
    table: TableMapping, schema: dict[str, tuple[ColumnDef, ...]]
) -> dict[str, list[str]]:
    """SAP-Spalte -> die kanonischen Pflichtspalten, die ohne sie leer blieben.

    Eine Quellspalte kann mehrere tragen: ``DMBTR`` liefert ``amount_local`` und ueber die
    Ableitung auch ``amount_signed_local``. Die Meldung nennt dann beide – wer die Spalte
    nachliefert, soll wissen, was von ihr abhaengt.

    Abgeleitet aus ``canonical.sql``: jede Zielspalte ``NOT NULL`` ohne ``DEFAULT``. Fuer
    Zielspalten ohne eigene Zuordnung im Mapping (``bp_key``, ``item_key``,
    ``amount_signed_local``) sagt ``DERIVED_REQUIREMENTS``, woraus sie entstehen.

    Nebenziele (``tax_id.*``, ``TIBAN``, ``T052U``, ``ADR6``) stehen hier nicht: sie
    erzeugen Zeilen nur, wenn der Export das Feld liefert – eine fehlende Spalte heisst
    dort "keine Zeile", nicht "Tabelle nicht bildbar".
    """
    if not _is_main_target(table):
        return {}
    target = table.target
    inverse = _inverse(table)
    needed: dict[str, list[str]] = {}
    for column in schema[target]:
        if not column.required:
            continue
        parts = DERIVED_REQUIREMENTS.get(target, {}).get(column.name, (column.name,))
        for part in parts:
            source = inverse.get(part)
            if source is None:
                raise CanonicalError(
                    f"{table.name}: die Pflichtspalte {target}.{column.name} hat im Mapping "
                    f"keine Quelle (gesucht: {part}). Zuordnung in sap_ecc.yaml ergaenzen "
                    "oder in DERIVED_REQUIREMENTS beschreiben."
                )
            needed.setdefault(source, []).append(column.name)
    return needed


def _check_required(
    mapping: Mapping,
    schema: dict[str, tuple[ColumnDef, ...]],
    available: dict[str, tuple[str, ...]],
) -> None:
    """Harter Abbruch, wenn eine Pflicht-Quellspalte fehlt – mit Tabelle und Spalte.

    Anders als beim Staging ist das kein Hinweis: ohne ``DMBTR`` gaebe es kein
    ``fi_item.amount_local``, und ein Lauf auf der halben Wahrheit ist schlimmer als
    keiner (Regel 4). Alle Luecken werden gemeinsam gemeldet.
    """
    problems: list[str] = []
    for table in mapping.staged_tables:
        columns = available.get(table.name)
        if columns is None:
            continue
        for source, target_columns in sorted(required_sources(table, schema).items()):
            if source not in columns:
                named = ", ".join(f"{table.target}.{name}" for name in target_columns)
                problems.append(
                    f"{table.name}: Pflichtspalte {source} fehlt in staged_{table.name} – "
                    f"sie liefert {named} (NOT NULL)."
                )
    if problems:
        raise CanonicalError(
            "Die Stufe canonical kann nicht gebildet werden:\n  " + "\n  ".join(problems)
        )


def _prefixed(expression: str, prefix: str) -> str:
    """Partnerschluessel mit Rollenpraefix; ein leerer Schluessel bleibt leer, nicht ``C:``."""
    return (
        f"CASE WHEN nullif(trim({expression}), '') IS NULL THEN NULL "
        f"ELSE '{prefix}' || {expression} END"
    )


def _expression(
    target: str,
    column: ColumnDef,
    table: TableMapping,
    available: tuple[str, ...],
    helpers: tuple[str, ...],
) -> str:
    """SQL-Ausdruck fuer eine kanonische Spalte – ``NULL``, wenn die Quelle sie nicht kennt."""
    prefix = ROLE_PREFIX[table.role] if table.role else ""
    inverse = _inverse(table)

    if column.name in DEFERRED_TO_SPRINT_4:
        return "NULL"  # Normalisierung kommt mit der Dubletten-Spec (Sprint 4)
    if target == "business_partner":
        if column.name == "bp_key":
            return _prefixed(f's."{inverse["source_id"]}"', prefix)
        if column.name == "role":
            return f"'{table.role}'"
        if column.name == "email":
            return 'e."email"' if "email" in helpers else "NULL"
    if target == "bp_bank_account" and column.name in ("iban", "iban_norm", "iban_valid",
                                                       "valid_from"):
        return f'b."{column.name}"' if "iban" in helpers else "NULL"
    if target == "payment_terms" and column.name == "description":
        return 'u."description"' if "description" in helpers else "NULL"
    if target == "fi_item":
        if column.name == "item_key":
            keys = ("company_code", "fiscal_year", "document_no", "line_item")
            joined = " || '|' || ".join(f's."{inverse[key]}"' for key in keys)
            return joined
        if column.name == "is_open":
            return "TRUE" if table.is_open else "FALSE"

    # Die abgeleiteten Spalten des Stagings heissen dort bereits kanonisch und werden
    # unveraendert uebernommen: amount_signed_local (D-009), reference_norm (D-065).
    if column.name in available:
        return f's."{column.name}"'

    source = inverse.get(column.name)
    if source is None or source not in available:
        # Der Vorgabewert kommt aus dem Schema, nicht aus einer Annahme im Code: eine
        # nicht gelieferte Spalte darf eine NOT-NULL-Zusage nicht brechen.
        return column.default if column.not_null and column.has_default else "NULL"
    expression = f's."{source}"'
    if column.name in PREFIXED_TARGETS and prefix:
        return _prefixed(expression, prefix)
    if column.not_null and column.has_default:
        # Das Staging laesst ein nicht gesetztes Kennzeichen NULL; das kanonische Schema
        # verlangt den Vorgabewert. Der Ort dieser Umsetzung steht im Mapping als Kommentar.
        return f"coalesce({expression}, {column.default})"
    return expression


def _empty_reason(target: str, column: ColumnDef, table: TableMapping) -> str:
    """Grund fuer eine leere Pflichtspalte – nennt Feld und Quellspalte, nie den Wert."""
    inverse = _inverse(table)
    parts = DERIVED_REQUIREMENTS.get(target, {}).get(column.name, (column.name,))
    sources = ", ".join(inverse[part] for part in parts if part in inverse)
    origin = f" ({sources})" if sources else ""
    return (
        f"CASE WHEN \"{column.name}\" IS NULL THEN "
        f"'{target}.{column.name} ist leer{origin}' END"
    )


# --- Hilfstabellen: E-Mail, IBAN, Zahlungsbedingungstext -------------------------------


def _staged_columns(con: duckdb.DuckDBPyConnection) -> dict[str, tuple[str, ...]]:
    """Die gestagten Tabellen mit ihren Spalten: ``staged_KNA1`` -> ``KNA1``."""
    rows = con.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_name LIKE 'staged_%' ORDER BY table_name, ordinal_position"
    ).fetchall()
    columns: dict[str, list[str]] = {}
    for table_name, column in rows:
        columns.setdefault(table_name[len("staged_") :], []).append(column)
    return {name: tuple(values) for name, values in columns.items()}


def _build_email(con: duckdb.DuckDBPyConnection, available: dict[str, tuple[str, ...]]) -> list[str]:
    """ADR6 zu einer E-Mail je Adressnummer – mehrere werden gemeldet, nicht verschwiegen."""
    if "ADR6" not in available:
        return []
    con.execute(
        'CREATE OR REPLACE TEMP TABLE __mdq_email AS '
        'SELECT "ADDRNUMBER" AS address_id, min("SMTP_ADDR") AS email, '
        'count(DISTINCT "SMTP_ADDR") AS variants '
        'FROM "staged_ADR6" WHERE nullif(trim("SMTP_ADDR"), \'\') IS NOT NULL '
        'AND "ADDRNUMBER" IS NOT NULL GROUP BY 1'
    )
    ambiguous = con.execute(
        "SELECT count(*) FROM __mdq_email WHERE variants > 1"
    ).fetchone()[0]
    if ambiguous:
        return [
            (
                f"ADR6: {ambiguous} Adressnummern tragen mehr als eine E-Mail – "
                "uebernommen wird die alphabetisch erste."
            )
        ]
    return []


def _build_iban(con: duckdb.DuckDBPyConnection, available: dict[str, tuple[str, ...]]) -> list[str]:
    """TIBAN zu einer IBAN je Bankschluessel: die juengste ``VALID_FROM`` gewinnt (D-078).

    Zwei Zeilen mit demselben ``VALID_FROM`` und verschiedenen IBAN sind mehrdeutig; die
    Bankverbindung wird dann nicht gebildet, sondern abgelehnt. Offener Punkt: ein
    ``VALID_FROM`` in der Zukunft gewinnt derzeit mit – sobald ``data_as_of`` bekannt ist
    (Aufgabe 4), wird auf ``max(VALID_FROM <= data_as_of)`` nachgeschaerft.
    """
    if "TIBAN" not in available:
        return []
    con.execute(
        'CREATE OR REPLACE TEMP TABLE __mdq_iban AS '
        "WITH rows AS ("
        '  SELECT "BANKS" AS bank_country, "BANKL" AS bank_key, "BANKN" AS account_number,'
        '         coalesce("BKONT", \'\') AS control_key, "IBAN" AS iban,'
        '         "iban_norm" AS iban_norm, "VALID_FROM" AS valid_from'
        '  FROM "staged_TIBAN" WHERE nullif(trim("IBAN"), \'\') IS NOT NULL'
        "), latest AS ("
        "  SELECT *, max(valid_from) OVER ("
        "    PARTITION BY bank_country, bank_key, account_number, control_key"
        "  ) AS newest FROM rows"
        ") "
        "SELECT bank_country, bank_key, account_number, control_key, "
        "min(iban) AS iban, min(iban_norm) AS iban_norm, max(valid_from) AS valid_from, "
        "count(DISTINCT iban_norm) > 1 AS ambiguous "
        "FROM latest WHERE valid_from IS NOT DISTINCT FROM newest "
        "GROUP BY 1, 2, 3, 4"
    )
    _build_iban_validity(con)
    return []


def _build_iban_validity(con: duckdb.DuckDBPyConnection) -> None:
    """Prueft die IBAN-Pruefziffern mit schwifty – je eindeutigem Wert genau einmal (D-073).

    Bewusst keine DuckDB-UDF: die kostet rund 75 Mikrosekunden je Wert an der
    Sprachgrenze (D-071). Hier sind es einige tausend eindeutige IBAN, in Python
    gerechnet und als Tabelle zurueckgegeben.
    """
    values = [
        row[0]
        for row in con.execute(
            "SELECT DISTINCT iban_norm FROM __mdq_iban WHERE iban_norm IS NOT NULL "
            "ORDER BY iban_norm"
        ).fetchall()
    ]
    con.execute(
        "CREATE OR REPLACE TEMP TABLE __mdq_iban_valid (iban_norm TEXT, valid BOOLEAN)"
    )
    if not values:
        return
    con.executemany(
        "INSERT INTO __mdq_iban_valid VALUES (?, ?)",
        [(value, is_valid_iban(value)) for value in values],
    )
    con.execute(
        "CREATE OR REPLACE TEMP TABLE __mdq_iban AS "
        "SELECT i.bank_country, i.bank_key, i.account_number, i.control_key, i.iban, "
        "i.iban_norm, i.valid_from, i.ambiguous, v.valid AS iban_valid "
        "FROM __mdq_iban i LEFT JOIN __mdq_iban_valid v ON v.iban_norm = i.iban_norm"
    )


def is_valid_iban(value: str | None) -> bool | None:
    """Pruefziffer und Laenderformat der IBAN; ``None``, wenn keine IBAN vorliegt."""
    if value is None or not value.strip():
        return None
    try:
        IBAN(value)
    except SchwiftyException:
        return False
    return True


def _build_terms_text(
    con: duckdb.DuckDBPyConnection, available: dict[str, tuple[str, ...]]
) -> list[str]:
    """T052U zu einem Text je Zahlungsbedingung – Deutsch vor Englisch vor Rest (D-074)."""
    if "T052U" not in available:
        return []
    order = " ".join(
        f"WHEN '{code}' THEN {index}" for index, code in enumerate(LANGUAGE_ORDER)
    )
    con.execute(
        "CREATE OR REPLACE TEMP TABLE __mdq_terms_text AS "
        "SELECT terms_key, description FROM ("
        '  SELECT "ZTERM" AS terms_key, "TEXT1" AS description,'
        "         row_number() OVER (PARTITION BY \"ZTERM\" ORDER BY "
        f'           CASE "SPRAS" {order} ELSE {len(LANGUAGE_ORDER)} END, "SPRAS"'
        "         ) AS rank"
        '  FROM "staged_T052U" WHERE nullif(trim("TEXT1"), \'\') IS NOT NULL'
        ") WHERE rank = 1"
    )
    return []


# --- Scope -----------------------------------------------------------------------------


def _bp_key_expression(table: TableMapping, available: tuple[str, ...]) -> str | None:
    """Der ``bp_key`` einer Quellzeile – ``None``, wenn die Tabelle keinen Partner nennt."""
    if not table.role:
        return None
    inverse = _inverse(table)
    source = inverse.get("bp_key")
    if source is None and table.target == "business_partner":
        source = inverse.get("source_id")
    if source is None or source not in available:
        return None
    return _prefixed(f's."{source}"', ROLE_PREFIX[table.role])


def _in_list(values: tuple[str, ...]) -> str:
    """Werteliste fuer ``IN`` – Schluessel sind Text, Anfuehrungszeichen werden verdoppelt."""
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)


def _build_scope_keys(
    con: duckdb.DuckDBPyConnection,
    mapping: Mapping,
    available: dict[str, tuple[str, ...]],
    scope: Scope,
) -> None:
    """Die Partner, die ueber ``--company-codes`` im Scope liegen.

    Ein Partner gehoert zum Lauf, wenn er mindestens eine Buchungskreiszeile im Scope hat.
    Ohne ``--company-codes`` wird die Tabelle nicht gebraucht und nicht gebaut.
    """
    if not scope.company_codes:
        return
    selects = []
    for table in mapping.staged_tables:
        if table.target != "bp_company_code" or table.role not in scope.roles:
            continue
        columns = available.get(table.name)
        if columns is None:
            continue
        key = _bp_key_expression(table, columns)
        code = _inverse(table).get("company_code")
        if key is None or code is None or code not in columns:
            continue
        selects.append(
            f'SELECT DISTINCT {key} AS bp_key FROM "staged_{table.name}" s '
            f'WHERE s."{code}" IN ({_in_list(scope.company_codes)})'
        )
    body = " UNION ".join(selects) if selects else "SELECT NULL AS bp_key WHERE FALSE"
    con.execute(f"CREATE OR REPLACE TEMP TABLE __mdq_scope_bp AS {body}")


def _scope_clauses(
    table: TableMapping, available: tuple[str, ...], scope: Scope
) -> list[str]:
    """Der Scope-Filter einer Quelltabelle – er greift **vor** der Referenzpruefung (D-075)."""
    clauses: list[str] = []
    inverse = _inverse(table)
    if scope.company_codes:
        code = inverse.get("company_code")
        key = _bp_key_expression(table, available)
        if code is not None and code in available:
            clauses.append(f's."{code}" IN ({_in_list(scope.company_codes)})')
        elif key is not None:
            clauses.append(f"EXISTS (SELECT 1 FROM __mdq_scope_bp k WHERE k.bp_key = {key})")
    if table.target == "fi_item":
        posting = inverse.get("posting_date")
        if posting is not None and posting in available:
            if scope.item_window_from is not None:
                clauses.append(f"s.\"{posting}\" >= DATE '{scope.item_window_from.isoformat()}'")
            if scope.item_window_to is not None:
                clauses.append(f"s.\"{posting}\" <= DATE '{scope.item_window_to.isoformat()}'")
    return clauses


# --- Der Bau einer Zieltabelle ---------------------------------------------------------


def _from_sql(table: TableMapping, available: tuple[str, ...], helpers: tuple[str, ...]) -> str:
    """FROM-Teil einer Quelle samt der Joins auf die Hilfstabellen."""
    parts = [f'"staged_{table.name}" s']
    inverse = _inverse(table)
    if table.target == "business_partner" and "email" in helpers:
        address = inverse.get("address_id")
        if address is not None and address in available:
            parts.append(f'LEFT JOIN __mdq_email e ON e.address_id = s."{address}"')
    if table.target == "bp_bank_account" and "iban" in helpers:
        join = table.join.get("TIBAN", ())
        if all(column in available for column in join):
            on = (
                'b.bank_country = s."BANKS" AND b.bank_key = s."BANKL" '
                'AND b.account_number = s."BANKN" '
                'AND b.control_key = coalesce(s."BKONT", \'\')'
            )
            parts.append(f"LEFT JOIN __mdq_iban b ON {on}")
    if table.target == "payment_terms" and "description" in helpers:
        terms = inverse.get("terms_key")
        if terms is not None and terms in available:
            parts.append(f'LEFT JOIN __mdq_terms_text u ON u.terms_key = s."{terms}"')
    return " ".join(parts)


def _key_text(keys: tuple[str, ...]) -> str:
    """Die Schluesselwerte einer Zeile als Text – fuer Meldungen, die die Zeile benennen."""
    return " || '|' || ".join(f'coalesce("{key}", \'\')' for key in keys)


def _reasons(
    target: str,
    table: TableMapping,
    schema: dict[str, tuple[ColumnDef, ...]],
    columns: list[tuple[str, str]],
    helpers: tuple[str, ...],
) -> list[str]:
    """Alle Gruende, aus denen eine Zeile nicht kanonisch werden kann – in fester Reihenfolge."""
    filled = {name for name, expression in columns if expression != "NULL"}
    reasons = [
        _empty_reason(target, column, table)
        for column in schema[target]
        if column.required and column.name in filled
    ]
    if target == "bp_bank_account" and "iban" in helpers:
        reasons.append(
            "CASE WHEN \"__ambiguous\" THEN 'TIBAN: mehrere IBAN mit demselben VALID_FROM – "
            "die Bankverbindung ist nicht eindeutig bestimmbar' END"
        )
    if target != "business_partner" and "bp_key" in filled:
        reasons.append(
            'CASE WHEN "bp_key" IS NOT NULL AND NOT EXISTS ('
            "SELECT 1 FROM business_partner bp WHERE bp.bp_key = t.\"bp_key\") "
            "THEN 'Stammsatz fehlt: ' || \"bp_key\" || ' steht nicht in business_partner' END"
        )
    keys = PRIMARY_KEYS.get(target)
    if keys and all(key in filled for key in keys):
        partition = ", ".join(f'"{key}"' for key in keys)
        reasons.append(
            f"CASE WHEN count(*) OVER (PARTITION BY {partition}) > 1 THEN "
            f"'{'/'.join(keys)} ' || {_key_text(keys)} || ' kommt in {table.name} mehrfach "
            "vor – keine der Zeilen wird uebernommen' END"
        )
        exists = " AND ".join(f'x."{key}" = t."{key}"' for key in keys)
        reasons.append(
            f'CASE WHEN EXISTS (SELECT 1 FROM "{target}" x WHERE {exists}) THEN '
            f"'{'/'.join(keys)} ' || {_key_text(keys)} || ' steht bereits aus einer anderen "
            f"Quelltabelle in {target}' END"
        )
    return reasons


def _insert_from_source(
    con: duckdb.DuckDBPyConnection,
    *,
    target: str,
    table: TableMapping,
    schema: dict[str, tuple[ColumnDef, ...]],
    available: dict[str, tuple[str, ...]],
    helpers: tuple[str, ...],
    scope: Scope,
    run_id: str,
) -> tuple[int, int, int]:
    """Fuellt ``target`` aus einer Quelltabelle. Ergebnis: (Zeilen, Rejects, ausserhalb Scope)."""
    columns_available = available[table.name]
    columns = [
        (column.name, _expression(target, column, table, columns_available, helpers))
        for column in schema[target]
    ]
    extra: list[tuple[str, str]] = []
    if target == "bp_bank_account" and "iban" in helpers:
        extra.append(("__ambiguous", "coalesce(b.ambiguous, FALSE)"))

    clauses = _scope_clauses(table, columns_available, scope)
    where = " AND ".join(clauses) if clauses else "TRUE"
    selection = ", ".join(
        [f's."{ROW_NO_COLUMN}" AS "{ROW_NO_COLUMN}"']
        + [f'{expression} AS "{name}"' for name, expression in columns + extra]
    )
    reasons = _reasons(target, table, schema, columns, helpers)
    reason_sql = f"coalesce({', '.join(reasons)})" if reasons else "NULL"

    work = f"__mdq_canon_{target}_{table.name}"
    con.execute(
        f'CREATE OR REPLACE TEMP TABLE "{work}" AS SELECT t.*, {reason_sql} AS "{REASON_COLUMN}" '
        f"FROM (SELECT {selection} FROM {_from_sql(table, columns_available, helpers)} "
        f"WHERE {where}) t"
    )
    names = ", ".join(f'"{name}"' for name, _ in columns)
    con.execute(
        f'INSERT INTO "{target}" ({names}) SELECT {names} FROM "{work}" '
        f'WHERE "{REASON_COLUMN}" IS NULL ORDER BY "{ROW_NO_COLUMN}"'
    )
    con.execute(
        "INSERT INTO reject (run_id, stage, source_table, row_no, reason, raw_excerpt) "
        f'SELECT ?, ?, ?, "{ROW_NO_COLUMN}", "{REASON_COLUMN}", NULL FROM "{work}" '
        f'WHERE "{REASON_COLUMN}" IS NOT NULL ORDER BY "{ROW_NO_COLUMN}"',
        [run_id, STAGE, table.name],
    )
    rows, rejected = con.execute(
        f'SELECT count(*) FILTER (WHERE "{REASON_COLUMN}" IS NULL), '
        f'count(*) FILTER (WHERE "{REASON_COLUMN}" IS NOT NULL) FROM "{work}"'
    ).fetchone()
    staged_rows = con.execute(f'SELECT count(*) FROM "staged_{table.name}"').fetchone()[0]
    con.execute(f'DROP TABLE "{work}"')
    return rows, rejected, staged_rows - rows - rejected


def _insert_tax_ids(
    con: duckdb.DuckDBPyConnection,
    table: TableMapping,
    available: dict[str, tuple[str, ...]],
    scope: Scope,
    run_id: str,
) -> tuple[int, int, int]:
    """Fuellt ``bp_tax_id`` aus den ``tax_id.*``-Feldern einer Stammtabelle.

    Anders als die Hauptziele entsteht hier je gefuelltem Feld eine Zeile; ein Feld, das
    der Export nicht liefert, heisst schlicht "keine Zeile dieser Art" und ist deshalb
    keine Pflichtspalte. ``country`` bleibt leer: KNAS/LFAS werden nicht gelesen, und das
    Land aus dem Praefix des Wertes zu schliessen waere genau die Behauptung, die
    AR-VAL-001 pruefen soll (D-076).
    """
    columns = available[table.name]
    key = _bp_key_expression(table, columns)
    if key is None:
        return 0, 0, 0
    fields = sorted(
        (target[len(TAX_ID_PREFIX) :], source)
        for source, target in table.fields.items()
        if target.startswith(TAX_ID_PREFIX)
    )
    clauses = _scope_clauses(table, columns, scope)
    where = " AND ".join(clauses) if clauses else "TRUE"
    rows = rejected = out_of_scope = 0
    for tax_type, source in fields:
        if source not in columns or f"{source}_norm" not in columns:
            continue
        selection = (
            f's."{ROW_NO_COLUMN}" AS "{ROW_NO_COLUMN}", {key} AS "bp_key", '
            f"'{tax_type}' AS \"tax_id_type\", NULL AS \"country\", "
            f's."{source}" AS "value", s."{source}_norm" AS "value_norm"'
        )
        reason = (
            'CASE WHEN "bp_key" IS NOT NULL AND NOT EXISTS ('
            "SELECT 1 FROM business_partner bp WHERE bp.bp_key = t.\"bp_key\") "
            "THEN 'Stammsatz fehlt: ' || \"bp_key\" || ' steht nicht in business_partner' END"
        )
        work = f"__mdq_canon_tax_{table.name}_{tax_type}"
        con.execute(
            f'CREATE OR REPLACE TEMP TABLE "{work}" AS SELECT t.*, {reason} AS "{REASON_COLUMN}" '
            f'FROM (SELECT {selection} FROM "staged_{table.name}" s WHERE {where} '
            f'AND nullif(trim(s."{source}"), \'\') IS NOT NULL) t'
        )
        names = '"bp_key", "tax_id_type", "country", "value", "value_norm"'
        con.execute(
            f'INSERT INTO bp_tax_id ({names}) SELECT {names} FROM "{work}" '
            f'WHERE "{REASON_COLUMN}" IS NULL ORDER BY "{ROW_NO_COLUMN}"'
        )
        con.execute(
            "INSERT INTO reject (run_id, stage, source_table, row_no, reason, raw_excerpt) "
            f'SELECT ?, ?, ?, "{ROW_NO_COLUMN}", "{REASON_COLUMN}", NULL FROM "{work}" '
            f'WHERE "{REASON_COLUMN}" IS NOT NULL ORDER BY "{ROW_NO_COLUMN}"',
            [run_id, STAGE, table.name],
        )
        added, denied = con.execute(
            f'SELECT count(*) FILTER (WHERE "{REASON_COLUMN}" IS NULL), '
            f'count(*) FILTER (WHERE "{REASON_COLUMN}" IS NOT NULL) FROM "{work}"'
        ).fetchone()
        con.execute(f'DROP TABLE "{work}"')
        rows += added
        rejected += denied
    return rows, rejected, out_of_scope


# --- Die Stufe -------------------------------------------------------------------------


def _unknown_vat_prefixes(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Praefixe in `bp_tax_id`, zu denen `vat_id_patterns.yaml` kein Muster kennt.

    Die Formatregeln (AR-VAL-002/AP-VAL-002) beurteilen solche Werte nicht: ohne Muster
    ist "falsch" eine Behauptung, nicht ein Befund. Verschwiegen wird das trotzdem nicht
    (Regel 4) – der Lauf nennt Praefix und Anzahl, damit das Muster beim Onboarding
    ergaenzt wird (D-101). Genannt werden nur Praefix und Zahl, nie ein Wert: eine
    USt-IdNr. ist eine Geschaeftspartnerangabe (Regel 8).
    """
    try:
        patterns = load_vat_patterns()
    except DictionaryError as exc:
        raise CanonicalError(str(exc)) from exc

    rows = con.execute(
        """
        SELECT substr(value_norm, 1, 2) AS praefix, count(*) AS anzahl
        FROM bp_tax_id
        WHERE tax_id_type = 'VAT'
          AND regexp_matches(substr(value_norm, 1, 2), '^[A-Z]{2}$')
        GROUP BY 1
        ORDER BY 1
        """
    ).fetchall()
    unbekannt = [(prefix, count) for prefix, count in rows if prefix not in patterns.patterns]
    if not unbekannt:
        return []
    genannt = ", ".join(f"{count} mit Präfix {prefix}" for prefix, count in unbekannt)
    return [
        (
            f"bp_tax_id: {genannt} – zu diesen Präfixen kennt {patterns.path.name} kein "
            "Muster. Die Formatregeln prüfen solche Werte nicht; Muster beim Onboarding "
            "ergänzen, dann greifen sie."
        )
    ]


def build_canonical(
    con: duckdb.DuckDBPyConnection,
    mapping: Mapping,
    run_id: str,
    scope: Scope | None = None,
    schema_path: Path = CANONICAL_SCHEMA,
) -> CanonicalResult:
    """Baut aus den gestagten Tabellen das kanonische Modell.

    Die Reihenfolge ist fest (``TARGET_ORDER``): der Stammsatz steht, bevor etwas auf ihn
    verweist, und zwei Laeufe ueber dieselben Daten fuellen die Tabellen zeilengleich
    (Regel 9).
    """
    scope = scope or Scope()
    schema = parse_schema(schema_path)
    available = _staged_columns(con)
    _check_required(mapping, schema, available)

    warnings: list[str] = []
    helpers: list[str] = []
    warnings.extend(_build_email(con, available))
    if "ADR6" in available:
        helpers.append("email")
    warnings.extend(_build_iban(con, available))
    if "TIBAN" in available:
        helpers.append("iban")
    warnings.extend(_build_terms_text(con, available))
    if "T052U" in available:
        helpers.append("description")
    _build_scope_keys(con, mapping, available, scope)

    warnings.append(
        "business_partner: " + ", ".join(DEFERRED_TO_SPRINT_4) + " bleiben leer – die "
        "Normalisierung von Name und Adresse definiert die Dubletten-Spec (Sprint 4). "
        "Keine Regel dieses Sprints liest sie."
    )

    results: list[TableResult] = []
    for target in TARGET_ORDER:
        sources = [
            table
            for table in mapping.staged_tables
            if _target_of(table, target)
            and table.name in available
            and (table.role is None or table.role in scope.roles)
        ]
        skipped = [
            table
            for table in mapping.staged_tables
            if _target_of(table, target)
            and table.name in available
            and table.role is not None
            and table.role not in scope.roles
        ]
        rows = rejected = out_of_scope = 0
        for table in sources:
            if target == "bp_tax_id":
                added, denied, outside = _insert_tax_ids(con, table, available, scope, run_id)
            else:
                added, denied, outside = _insert_from_source(
                    con,
                    target=target,
                    table=table,
                    schema=schema,
                    available=available,
                    helpers=tuple(helpers),
                    scope=scope,
                    run_id=run_id,
                )
            rows += added
            rejected += denied
            out_of_scope += outside
        for table in skipped:
            out_of_scope += con.execute(
                f'SELECT count(*) FROM "staged_{table.name}"'
            ).fetchone()[0]
        results.append(
            TableResult(
                table=target,
                rows=rows,
                rejected=rejected,
                out_of_scope=out_of_scope,
                sources=tuple(table.name for table in sources),
            )
        )

    warnings.extend(_unknown_vat_prefixes(con))

    delivered = _delivered_window(con, mapping, available)
    return CanonicalResult(
        scope=scope,
        tables=tuple(results),
        warnings=tuple(warnings),
        posting_date_from=delivered[0],
        posting_date_to=delivered[1],
    )


def _target_of(table: TableMapping, target: str) -> bool:
    """Fuellt diese Quelltabelle die genannte Zieltabelle?"""
    if target == "bp_tax_id":
        return any(value.startswith(TAX_ID_PREFIX) for value in table.fields.values())
    return table.target == target


def _delivered_window(
    con: duckdb.DuckDBPyConnection,
    mapping: Mapping,
    available: dict[str, tuple[str, ...]],
) -> tuple[date | None, date | None]:
    """Das tatsaechlich gelieferte Postenfenster – berichtet, nicht angewandt (Aufgabe 4)."""
    selects = []
    for table in mapping.staged_tables:
        if table.target != "fi_item" or table.name not in available:
            continue
        posting = _inverse(table).get("posting_date")
        if posting is not None and posting in available[table.name]:
            selects.append(f'SELECT "{posting}" AS d FROM "staged_{table.name}"')
    if not selects:
        return None, None
    first, last = con.execute(
        f"SELECT min(d), max(d) FROM ({' UNION ALL '.join(selects)})"
    ).fetchone()
    return first, last
