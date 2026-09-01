"""Staging: ``raw_<TABELLE>`` -> ``staged_<TABELLE>`` (typisiert).

Die zweite Stufe der Pipeline ``raw -> staged -> canonical -> findings`` (Regel 3). Aus den
reinen TEXT-Spalten der Rohtabelle werden Beträge, Datumswerte, Prozentsätze, Ganzzahlen
und Kennzeichen – nach der Typklasse, die ``logic/mappings/sap_ecc.yaml`` je SAP-Feld
festlegt. Die Spaltennamen bleiben die des Exports; die Umbenennung auf das kanonische
Schema macht das Mapping (Aufgabe 2). Dazu kommen die abgeleiteten Spalten, die genau hier
und nur hier entstehen: ``amount_signed_local`` (D-009), ``reference_norm`` (D-065),
``iban_norm`` und die normalisierten Steuer-IDs.

Gerechnet wird im SQL, mit den Makros aus ``logic/schema/staging.sql`` (D-071).
``formats.py`` bleibt die Referenz-Implementierung; dass beide gleich rechnen, prüft
``test_staging.py`` über einen festen Grenzfallsatz und über jeden Wert des Demo-Mandanten.

Die Auswertung läuft in **Schichten**: DuckDB setzt Makros textuell ein, und ein Aufruf wie
``mdq_parse_amount(mdq_clean(v))`` würde denselben Teilbaum vielfach kopieren, bis das
Binden Minuten kostet. Jede Schicht ist deshalb eine eigene Unterabfrage, die ihr Zwischen-
ergebnis als Spalte trägt – ein Makro sieht nur noch Spaltenverweise und läuft einmal je
Zeile.

Nicht lesbare Werte ergeben NULL statt eines Fehlers; die Zeile landet vollständig in
``reject`` (Stufe ``staged``) mit dem **ersten** fehlerhaften Feld als Grund, und der Lauf
läuft weiter (Regel 4). Der Grund nennt Feldname und Form, nie den Wert – der steht
ausschließlich in ``raw_excerpt`` (Regel 8, D-036).
"""

from dataclasses import dataclass, field
from decimal import Decimal

import duckdb

from mdq import STAGING_MACROS
from mdq.formats import DATE_INITIALS, NOTATIONS, detect_notation
from mdq.loader import RAW_EXCERPT_LIMIT, ROW_NO_COLUMN
from mdq.mapping import Mapping, TableMapping, missing_columns, unknown_columns

#: Präfixe der Zwischenspalten – SAP-Feldnamen fangen nie so an
SIGN_PREFIX = "__sign_"
CLEAN_PREFIX = "__clean_"
SEPARATOR_PREFIX = "__sep_"
LITERAL_PREFIX = "__lit_"
TYPED_PREFIX = "__t_"

#: Spalte mit dem Grund, an dem eine Zeile scheitert (NULL = Zeile ist sauber)
REASON_COLUMN = "__reject_reason"

#: Spalte mit dem Rohauszug für ``reject.raw_excerpt``
EXCERPT_COLUMN = "__raw_excerpt"

#: Stufe, unter der Rejects dieses Schritts in ``reject`` stehen
STAGE = "staged"

#: Grund je Typklasse – nennt die Form, nie den Wert (Regel 8)
REJECT_REASON = {
    "amount": "Betrag nicht als DECIMAL(15,2) lesbar",
    "percent": "Prozentsatz nicht als DECIMAL(5,3) lesbar",
    "date": "Datum nicht lesbar",
    "integer": "Ganzzahl nicht lesbar",
    "flag": 'Kennzeichen ist weder leer noch "X"',
}

#: Soll und Haben; alles andere macht ``amount_signed_local`` zur Vermutung
DEBIT_CREDIT = ("S", "H")

#: Gesamtstellen und Nachkommastellen je Typklasse, wie im kanonischen Schema.
#: Nur diese beiden Klassen werden über die Dezimalauswertung in Schichten gelesen.
DECIMAL_PRECISION = {"amount": (15, 2), "percent": (5, 3)}


class StagingError(ValueError):
    """Das Staging kann eine Tabelle nicht lesen – der Lauf bricht ab."""


@dataclass(frozen=True)
class AmountTotal:
    """Kontrollsumme: ``amount_signed_local`` je Buchungskreis und Währung."""

    company_code: str | None
    currency: str | None
    #: Betrag als Text mit zwei Dezimalen – nie float (Regel 2)
    amount: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "company_code": self.company_code,
            "currency": self.currency,
            "amount": self.amount,
        }


@dataclass(frozen=True)
class StageResult:
    """Ergebnis einer gestagten Tabelle – Grundlage der Kontrollsummen im Run-Report."""

    table: str
    rows_raw: int
    rows_staged: int
    rejected: int
    notation: str | None
    notation_source: str
    totals: tuple[AmountTotal, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "table": self.table,
            "rows_raw": self.rows_raw,
            "rows_staged": self.rows_staged,
            "rejected": self.rejected,
            "notation": self.notation,
            "notation_source": self.notation_source,
            "totals": [total.to_dict() for total in self.totals],
            "warnings": list(self.warnings),
        }


# --- Die Makros aus logic/schema/staging.sql -------------------------------------------


def install_macros(con: duckdb.DuckDBPyConnection) -> None:
    """Legt die Staging-Makros in der Verbindung an.

    Sie stehen in ``logic/`` und nicht in Python: die Typisierung ist fachliche Logik,
    und sie wird im SQL ausgeführt (D-071).
    """
    con.execute(STAGING_MACROS.read_text(encoding="utf-8"))


# --- Notation je Datei (D-035) ---------------------------------------------------------


def detect_table_notation(
    con: duckdb.DuckDBPyConnection, table: TableMapping, mapping: Mapping
) -> str | None:
    """Notation der Datei aus den eindeutigen Beträgen ihrer Betragsspalten.

    Prozentfelder zählen nicht mit: ihre Notation kommt aus dem Feld, nicht aus der Datei
    (D-048). Widersprechen sich zwei Spalten, bricht der Lauf ab – ein SE16N-Export folgt
    einer Benutzereinstellung, und zwei Notationen in einer Datei heißen, dass die Datei
    nicht das ist, wofür sie gehalten wird.
    """
    raw_table = f"raw_{table.name}"
    delivered = {
        name
        for (name,) in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
            [raw_table],
        ).fetchall()
    }
    found: dict[str, str] = {}
    for column in table.columns:
        if mapping.type_of(column) != "amount" or column not in delivered:
            continue
        values = con.execute(
            f'SELECT DISTINCT "{column}" FROM "{raw_table}" WHERE "{column}" IS NOT NULL'
        ).fetchall()
        notation = detect_notation(value for (value,) in values)
        if notation is None:
            continue
        for other, other_notation in found.items():
            if other_notation != notation:
                raise StagingError(
                    f"{table.name}: die Spalten {other} und {column} widersprechen sich in "
                    f"der Dezimalnotation ({other_notation} gegen {notation}). Ein Export "
                    "folgt einer Benutzereinstellung und hat genau eine Notation; die "
                    "Datei muss geklärt werden, bevor sie gelesen werden kann."
                )
        found[column] = notation
    return next(iter(found.values()), None)


# --- SQL-Bau ---------------------------------------------------------------------------


def typed_layers(
    columns: list[tuple[str, str]], notation: str | None
) -> list[list[tuple[str, str]]]:
    """Die Schichten der Typisierung: je Schicht ``(Spaltenname, SQL-Ausdruck)``.

    Beträge und Prozentsätze brauchen vier Schritte – Vorzeichen und bereinigter Wert,
    Dezimaltrenner, Zahlliteral, geprüfte Umwandlung. Jeder Schritt liest nur Spalten der
    Schicht darunter, nie einen verschachtelten Makroaufruf: sonst kopiert DuckDB beim
    Einsetzen denselben Teilbaum immer wieder (siehe Modul-Docstring). Datum, Ganzzahl und
    Kennzeichen kommen ohne Zwischenschritte aus und stehen in der letzten Schicht.
    """
    decimals = [(name, kind) for name, kind in columns if kind in DECIMAL_PRECISION]
    simple = [(name, kind) for name, kind in columns if kind not in DECIMAL_PRECISION]

    prepare: list[tuple[str, str]] = []
    for name, _ in decimals:
        prepare.append((f"{SIGN_PREFIX}{name}", f'mdq_sign("{name}")'))
        prepare.append((f"{CLEAN_PREFIX}{name}", f'mdq_clean("{name}")'))

    separators = [
        (
            f"{SEPARATOR_PREFIX}{name}",
            f"mdq_decimal_sep(\"{CLEAN_PREFIX}{name}\", '{notation or ''}')"
            if kind == "amount"
            else f'mdq_percent_sep("{CLEAN_PREFIX}{name}")',
        )
        for name, kind in decimals
    ]

    literals = [
        (
            f"{LITERAL_PREFIX}{name}",
            f'mdq_literal("{CLEAN_PREFIX}{name}", "{SEPARATOR_PREFIX}{name}")',
        )
        for name, _ in decimals
    ]

    typed: list[tuple[str, str]] = []
    for name, kind in decimals:
        total, decimal_places = DECIMAL_PRECISION[kind]
        typed.append(
            (
                f"{TYPED_PREFIX}{name}",
                (
                    f'CASE WHEN mdq_fits("{LITERAL_PREFIX}{name}", {total}, {decimal_places}) '
                    f'THEN TRY_CAST("{SIGN_PREFIX}{name}" || "{LITERAL_PREFIX}{name}" '
                    f"AS DECIMAL({total}, {decimal_places})) END"
                ),
            )
        )
    for name, kind in simple:
        typed.append((f"{TYPED_PREFIX}{name}", f'mdq_parse_{kind}("{name}")'))

    return [layer for layer in (prepare, separators, literals, typed) if layer]


def _stacked(inner_sql: str, layers: list[list[tuple[str, str]]]) -> str:
    """Legt die Schichten als ineinandergeschachtelte Unterabfragen übereinander."""
    sql = inner_sql
    for index, layer in enumerate(layers):
        additions = ", ".join(f'{expression} AS "{name}"' for name, expression in layer)
        sql = f"SELECT *, {additions} FROM ({sql}) AS schicht{index}"
    return sql


def parse_values(
    con: duckdb.DuckDBPyConnection,
    values: list[str | None],
    type_class: str,
    notation: str | None = None,
) -> list:
    """Liest eine Liste von Werten über dieselben Makros wie das Staging.

    Für den Äquivalenztest gegen ``formats.py`` und für die Fehlersuche an einer einzelnen
    Spalte – dieselben Ausdrücke, die auch die Tabellen typisieren.
    """
    # Die Liste kommt als ein Parameter in die Abfrage; zeilenweises INSERT waere hier der
    # teuerste Teil des Tests (rund 1 ms je Wert) und haette mit der Typisierung nichts zu tun.
    layers = typed_layers([("v", type_class)], notation)
    source = (
        'SELECT i, q.liste[i] AS v FROM (SELECT ?::VARCHAR[] AS liste) q, '
        "range(1, len(q.liste) + 1) r(i)"
    )
    rows = con.execute(
        f'SELECT "{TYPED_PREFIX}v" FROM ({_stacked(source, layers)}) AS werte ORDER BY i',
        [list(values)],
    ).fetchall()
    return [value for (value,) in rows]


def _initial_values(type_class: str) -> tuple[str, ...]:
    """Werte, die als SAP-Initialwert gelten und deshalb kein Reject sind (D-035)."""
    if type_class == "date":
        return ("", *sorted(DATE_INITIALS))
    return ("",)


def _reject_case(column: str, type_class: str) -> str:
    """NULL nach dem Parsen **und** kein Initialwert heißt: der Wert war nicht lesbar."""
    initials = ", ".join(f"'{value}'" for value in _initial_values(type_class))
    return (
        f'CASE WHEN "{TYPED_PREFIX}{column}" IS NULL '
        f"AND coalesce(trim(\"{column}\"), '') NOT IN ({initials}) "
        f"THEN '{column}: {REJECT_REASON[type_class]}' END"
    )


def _derived_columns(columns: tuple[str, ...]) -> list[tuple[str, str]]:
    """Die abgeleiteten Spalten des Stagings, in fester Reihenfolge.

    Klartext dazu steht unter ``derivations`` in ``logic/mappings/sap_ecc.yaml``; die
    Definitionen hier folgen ihm wörtlich. ``value_norm`` der Steuer-IDs entsteht je
    Quellspalte als ``<FELD>_norm`` – die Zeilenform in ``bp_tax_id`` baut erst das
    Mapping (Aufgabe 2).
    """
    derived: list[tuple[str, str]] = []
    if "SHKZG" in columns and "DMBTR" in columns:
        derived.append(
            (
                "amount_signed_local",
                (
                    f'CASE WHEN "SHKZG" = \'H\' THEN -"{TYPED_PREFIX}DMBTR" '
                    f'ELSE "{TYPED_PREFIX}DMBTR" END'
                ),
            )
        )
    if "XBLNR" in columns:
        derived.append(
            ("reference_norm", "upper(regexp_replace(\"XBLNR\", '[^A-Za-z0-9]', '', 'g'))")
        )
    if "IBAN" in columns:
        derived.append(("iban_norm", "upper(replace(\"IBAN\", ' ', ''))"))
    for tax_field in ("STCD1", "STCD2", "STCEG"):
        if tax_field in columns:
            derived.append(
                (
                    f"{tax_field}_norm",
                    f"upper(replace(replace(\"{tax_field}\", ' ', ''), '.', ''))",
                )
            )
    return derived


def _debit_credit_case(columns: tuple[str, ...]) -> str | None:
    """SHKZG entscheidet das Vorzeichen – ein dritter Wert wäre eine stille Vermutung."""
    if "SHKZG" not in columns:
        return None
    allowed = ", ".join(f"'{value}'" for value in DEBIT_CREDIT)
    return (
        f"CASE WHEN coalesce(trim(\"SHKZG\"), '') NOT IN ({allowed}) "
        f"THEN 'SHKZG: weder S noch H – das Vorzeichen von amount_signed_local "
        f"ist nicht bestimmbar' END"
    )


def _excerpt_expression(columns: tuple[str, ...]) -> str:
    """Rohauszug der Zeile – die einzige Stelle, an der Rohdaten stehen dürfen (Regel 8)."""
    parts = ", ".join(f"coalesce(\"{column}\", '')" for column in columns)
    return f"left(concat_ws(chr(9), {parts}), {RAW_EXCERPT_LIMIT})"


# --- Staging ---------------------------------------------------------------------------


def stage_table(
    con: duckdb.DuckDBPyConnection,
    mapping: Mapping,
    table_name: str,
    run_id: str,
    notation: str | None = None,
) -> StageResult:
    """Typisiert ``raw_<TABELLE>`` nach ``staged_<TABELLE>``.

    ``notation`` ist der Laufparameter ``--decimal-notation``; er greift nur, wenn die
    Datei selbst keinen eindeutigen Betrag enthält (D-035).
    """
    if notation is not None and notation not in NOTATIONS:
        raise StagingError(f"unbekannte Dezimalnotation {notation!r}; erlaubt {list(NOTATIONS)}")

    table = mapping.table(table_name)
    raw_table = f"raw_{table.name}"
    available = [
        name
        for (name,) in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ? "
            "ORDER BY ordinal_position",
            [raw_table],
        ).fetchall()
    ]
    if not available:
        raise StagingError(f"{table.name}: die Rohtabelle {raw_table} fehlt.")

    delivered = [name for name in available if name != ROW_NO_COLUMN]
    unknown = unknown_columns(table, delivered)
    if unknown:
        raise StagingError(
            f"{table.name}: unbekannte Spalten {unknown} – im Mapping unter fields "
            "aufnehmen oder unter ignore eintragen (Regel 4)."
        )

    warnings: list[str] = []
    absent = missing_columns(table, delivered)
    if absent:
        # Kein Abbruch: gestagt wird, was geliefert ist – aber die Luecke wird genannt.
        # Ob ein Feld fuer das kanonische Modell unverzichtbar ist, entscheidet Aufgabe 2.
        warnings.append(
            f"{table.name}: im Export fehlen gemappte Spalten {absent} – "
            f"sie fehlen damit auch in staged_{table.name}."
        )

    detected = detect_table_notation(con, table, mapping)
    if detected is not None:
        used, source = detected, "Datei"
        if notation is not None and notation != detected:
            warnings.append(
                f"{table.name}: --decimal-notation {notation} wurde nicht angewendet – die "
                f"Datei belegt selbst {detected}."
            )
    elif notation is not None:
        used, source = notation, "Parameter"
    else:
        used, source = None, "unbestimmt"

    columns = tuple(name for name in table.columns if name in delivered)
    typed_columns = [
        (column, mapping.type_of(column))
        for column in columns
        if mapping.type_of(column) != "text"
    ]
    reject_cases = [_reject_case(column, kind) for column, kind in typed_columns]
    debit_credit = _debit_credit_case(columns)
    if debit_credit is not None:
        reject_cases.append(debit_credit)

    derived = _derived_columns(columns)
    raw_selection = ", ".join([f'"{ROW_NO_COLUMN}"'] + [f'"{column}"' for column in columns])
    reason = f"coalesce({', '.join(reject_cases)})" if reject_cases else "NULL"

    # Die Typisierung Schicht fuer Schicht, darauf die abgeleiteten Spalten, der Grund und
    # der Rohauszug – alles in einer Anweisung, damit jede Zeile genau einmal gelesen wird.
    layers = typed_layers(typed_columns, used)
    layers.append(list(derived))
    layers.append(
        [
            (REASON_COLUMN, reason),
            (EXCERPT_COLUMN, _excerpt_expression(columns)),
        ]
    )
    work_table = f"__mdq_typed_{table.name}"
    con.execute(
        f'CREATE OR REPLACE TEMP TABLE "{work_table}" AS '
        + _stacked(f'SELECT {raw_selection} FROM "{raw_table}"', layers)
    )

    con.execute(
        "INSERT INTO reject (run_id, stage, source_table, row_no, reason, raw_excerpt) "
        f'SELECT ?, ?, ?, "{ROW_NO_COLUMN}", "{REASON_COLUMN}", "{EXCERPT_COLUMN}" '
        f'FROM "{work_table}" WHERE "{REASON_COLUMN}" IS NOT NULL '
        f'ORDER BY "{ROW_NO_COLUMN}"',
        [run_id, STAGE, table.name],
    )

    staged_selection = ", ".join(
        [f'"{ROW_NO_COLUMN}"']
        + [
            f'"{TYPED_PREFIX}{column}" AS "{column}"'
            if mapping.type_of(column) != "text"
            else f'"{column}"'
            for column in columns
        ]
        + [f'"{name}"' for name, _ in derived]
    )
    con.execute(
        f'CREATE OR REPLACE TABLE "staged_{table.name}" AS '
        f'SELECT {staged_selection} FROM "{work_table}" '
        f'WHERE "{REASON_COLUMN}" IS NULL ORDER BY "{ROW_NO_COLUMN}"'
    )
    con.execute(f'DROP TABLE "{work_table}"')

    rows_raw = con.execute(f'SELECT count(*) FROM "{raw_table}"').fetchone()[0]
    rows_staged = con.execute(f'SELECT count(*) FROM "staged_{table.name}"').fetchone()[0]
    return StageResult(
        table=table.name,
        rows_raw=rows_raw,
        rows_staged=rows_staged,
        rejected=rows_raw - rows_staged,
        notation=used,
        notation_source=source,
        totals=amount_totals(con, table.name, derived, columns),
        warnings=tuple(warnings),
    )


#: Quellspalten der Kontrollsumme: Buchungskreis und Belegwährung neben dem Betrag
TOTAL_COLUMNS = ("BUKRS", "WAERS")


def amount_totals(
    con: duckdb.DuckDBPyConnection,
    table_name: str,
    derived: list[tuple[str, str]],
    columns: tuple[str, ...],
) -> tuple[AmountTotal, ...]:
    """Summe ``amount_signed_local`` je Buchungskreis und Währung – R-4.

    Die Währung steht neben dem Betrag (Regel 2): ohne sie wäre die Summe eines Mandanten
    mit zwei Hauswährungen eine falsch etikettierte Zahl. Die Hauswährungsprüfung selbst
    kommt in Aufgabe 3 (D-030).

    ``columns`` sind die gelieferten gemappten Spalten der Tabelle. Fehlt eine der beiden
    Quellspalten, endet die Stufe mit Tabellen- und Spaltennamen statt mit einem nackten
    DuckDB-Fehler ohne Auskunft (Regel 4): eine Kontrollsumme ohne Buchungskreis oder
    ohne Währung ist keine.
    """
    if not any(name == "amount_signed_local" for name, _ in derived):
        return ()
    absent = [name for name in TOTAL_COLUMNS if name not in columns]
    if absent:
        raise StagingError(
            f"{table_name}: die Kontrollsumme über amount_signed_local braucht {absent}, "
            f"die Spalten fehlen in staged_{table_name}. Export vervollständigen."
        )
    rows = con.execute(
        f'SELECT "BUKRS", "WAERS", sum("amount_signed_local") FROM "staged_{table_name}" '
        "GROUP BY 1, 2 ORDER BY 1, 2"
    ).fetchall()
    return tuple(
        AmountTotal(
            company_code=company_code,
            currency=currency,
            amount=format(total or Decimal(0), ".2f"),
        )
        for company_code, currency, total in rows
    )


def stage_all(
    con: duckdb.DuckDBPyConnection,
    mapping: Mapping,
    table_names: list[str],
    run_id: str,
    notation: str | None = None,
) -> list[StageResult]:
    """Stagt die geladenen Tabellen, nach Namen sortiert (Determinismus, Regel 9)."""
    install_macros(con)
    return [
        stage_table(con, mapping, table_name, run_id, notation)
        for table_name in sorted(set(table_names))
        if mapping.table(table_name).is_staged
    ]
