"""Ausfuehrung einer Regel gegen DuckDB und Bau der Findings.

Der Ausgabe-Vertrag des SQL steht in ``logic/rules/README.md``. Alles, was die Regel nicht
liefert, ergaenzt diese Datei: Defaults aus dem Regelkopf, Versionen und Zeitpunkt aus dem
``RunContext``, Relevanz aus ``bp_relevance``. Jedes Finding wird gegen das Schema
validiert (CLAUDE.md, Regel 6).
"""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from functools import cache
from typing import Any

import duckdb

from mdq import RULE_MACROS
from mdq.decisions import DecisionMemory, apply_decision
from mdq.dictionaries import (
    PLACEHOLDER_TERMS_RE,
    VAT_PATTERN_PLACEHOLDER_RE,
    DictionaryError,
    DocumentTypes,
    PlaceholderTerms,
    VatPatterns,
    load_document_types,
    load_placeholder_terms,
    load_vat_patterns,
    substitute,
)
from mdq.findings import validate_finding
from mdq.relevance import multiple_currencies_message
from mdq.rules import Rule

#: Pflichtspalten des Ausgabe-Vertrags
REQUIRED_COLUMNS = ("bp_key", "role", "source_table", "source_field", "current_value")

#: Optionale Spalten des Ausgabe-Vertrags
OPTIONAL_COLUMNS = (
    "company_code",
    "current_display",
    "proposed_value",
    "proposed_display",
    "source_summary",
    "options",
    "tier",
    "action_type",
    "evidence",
    "impact_amount",
    "impact_currency",
    "impact_formula",
    "netted_against",
    "related_bp_keys",
    "documents",
    "records",
    "params",
    "finding_key",
)

#: Spalten, die in die finding_id eingehen – Reihenfolge ist Teil des Vertrags
ID_COLUMNS = (
    "bp_key",
    "company_code",
    "source_table",
    "source_field",
    "current_value",
    "finding_key",
)

#: Spalten, die als JSON aus dem SQL kommen
JSON_COLUMNS = ("options", "evidence", "related_bp_keys", "documents", "records", "params")

#: Felder des Regelkopfes, in denen {params}-Platzhalter gefuellt werden
TEMPLATED_FIELDS = ("title", "why", "if_wrong")


class ExecutionError(RuntimeError):
    """Die Regel konnte nicht ausgefuehrt werden oder verletzt den Ausgabe-Vertrag."""


class InvalidFindingError(ExecutionError):
    """Ein Finding ist nicht schema-valide – der Lauf schlaegt fehl (CLAUDE.md Regel 6).

    Eigene Klasse, weil der Lauf die beiden Faelle verschieden behandelt: eine Regel mit
    kaputtem SQL gilt als fehlgeschlagen und haelt die uebrigen nicht auf (Exit 1), ein
    ungueltiges Finding bricht den Lauf ab (Exit 2). Ein Lauf, der schema-ungueltige
    Findings ausliefert, ist schlimmer als keiner (D-098).
    """


@dataclass(frozen=True)
class RunContext:
    """Unveraenderliche Kopfdaten eines Laufs.

    ``created_at`` kommt bewusst von aussen und nie aus ``datetime.now()`` im Executor:
    gleicher Input muss identische Findings liefern (Regel 9, D-028).
    """

    run_id: str
    engine_version: str
    pack_version: str
    data_as_of: str
    created_at: str
    #: Gepflegte Entscheidungen des Kunden. Sie unterdruecken kein Finding, sie setzen
    #: seinen Status (D-088); ohne Gedaechtnis bleibt jedes Finding ``open``.
    decisions: DecisionMemory | None = None
    #: Belegartenklassen fuer die ``${doc_types...}``-Platzhalter im Regel-SQL (D-084);
    #: ohne Angabe gilt ``logic/dictionaries/document_types.yaml``.
    doc_types: DocumentTypes | None = None
    #: Formatmuster der USt-IdNr. fuer ``${vat_patterns.rows}`` (D-101); ohne Angabe gilt
    #: ``logic/dictionaries/vat_id_patterns.yaml``.
    vat_patterns: VatPatterns | None = None
    #: Platzhalterbegriffe fuer ``${placeholder_terms.pattern}`` (D-102); ohne Angabe gilt
    #: ``logic/dictionaries/placeholder_terms.yaml``.
    placeholder_terms: PlaceholderTerms | None = None
    #: Beginn des Postenfensters fuer ``${scope.item_window_from}`` (D-110). Aus dem Scope,
    #: sonst das fruehste Buchungsdatum der geladenen Posten; ``None``, wenn der Lauf keinen
    #: Posten enthaelt – dann kann eine Regel, die das Fenster braucht, nicht laufen.
    item_window_from: date | None = None


def finding_id_for(rule_id: str, row: dict[str, Any]) -> str:
    """Bildet die deterministische finding_id (D-027).

    `F-` + sha1 ueber rule_id und die Spalten aus ``ID_COLUMNS``, verbunden mit `|`,
    NULL als leerer Text.
    """
    parts = [rule_id]
    parts.extend("" if row.get(column) is None else str(row[column]) for column in ID_COLUMNS)
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return f"F-{digest[:12]}"


@cache
def _rule_macro_sql() -> str:
    """Die Darstellungshilfen fuer Regel-SQL – einmal gelesen (D-187)."""
    return RULE_MACROS.read_text(encoding="utf-8")


def ensure_rule_macros(con: duckdb.DuckDBPyConnection) -> None:
    """Legt ``mdq_money`` und Helfer in der Verbindung an.

    Bewusst hier und nicht im kanonischen Schema: es sind Darstellungshilfen, keine
    Tabellen – und sie muessen ueberall dort stehen, wo eine Regel laeuft, auch in einem
    Test, der nur das kanonische Schema geladen hat. ``CREATE OR REPLACE`` macht den
    wiederholten Aufruf billig und die Reihenfolge egal.

    **Das kanonische Schema muss vorher stehen.** ``mdq_payment_terms_text`` schlaegt in
    ``payment_terms`` nach, und DuckDB verlangt die Tabelle schon beim Anlegen des Makros
    (D-206). Fuer den Lauf ist das ohne Belang – dort wird das Schema als Erstes geladen –,
    fuer eine Verbindung, die nur die Makros haben will, ist es eine Vorbedingung.
    """
    con.execute(_rule_macro_sql())


@cache
def _default_doc_types() -> DocumentTypes:
    """Das Woerterbuch aus ``logic/`` – einmal gelesen, nicht je Regel neu."""
    return load_document_types()


@cache
def _default_vat_patterns() -> VatPatterns:
    """Die Formatmuster aus ``logic/`` – einmal gelesen, nicht je Regel neu."""
    return load_vat_patterns()


@cache
def _default_placeholder_terms() -> PlaceholderTerms:
    """Die Platzhalterbegriffe aus ``logic/`` – einmal gelesen, nicht je Regel neu."""
    return load_placeholder_terms()


#: Benannte Schwelle aus dem Regelkopf: ``${params.min_invoices}`` (D-107)
_PARAM_RE = re.compile(r"\$\{params\.([a-z][a-z0-9_]*)\}")

#: Beginn des Postenfensters: ``${scope.item_window_from}`` (D-110)
_WINDOW_RE = re.compile(r"\$\{scope\.item_window_from\}")

#: Datenstand des Laufs: ``${scope.data_as_of}``. Eine Regel, die "Frist verstrichen" oder
#: "letzte zwoelf Monate" braucht, darf dafuer **nicht** ``current_date`` nehmen: derselbe
#: Input muesste sonst morgen andere Findings liefern (Regel 9, D-028). Der Stichtag kommt
#: deshalb aus dem Lauf, wie der Fensterbeginn in D-110.
_DATA_AS_OF_RE = re.compile(r"\$\{scope\.data_as_of\}")


def _substitute_parameters(rule: Rule) -> str:
    """Setzt ``${params.<name>}`` aus dem Regelkopf ein (D-107).

    Eine Schwelle als Zahl im SQL waere nicht auffindbar und stuende in keinem Klartext;
    im Kopf hat sie einen Namen und faellt beim Lesen der Regel auf. Ein Platzhalter ohne
    Eintrag ist ein Fehler mit Namen, kein stiller Vorgabewert (Regel 4).
    """

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in rule.parameters:
            known = sorted(rule.parameters) or "keine"
            raise ExecutionError(
                f"{rule.id}: {match.group(0)} steht im SQL, aber nicht unter 'parameters' "
                f"im Regelkopf (dort steht: {known})."
            )
        return repr(rule.parameters[name])

    return _PARAM_RE.sub(replace, rule.sql)


def rule_sql(rule: Rule, ctx: RunContext) -> str:
    """Das auszufuehrende SQL: Schwellen und Belegartenlisten eingesetzt (D-084, D-107).

    Die Regel liest damit weiterhin nur das kanonische Schema; Liste und Schwelle kommen
    als Parameter, die Liste von der Engine, die Schwelle aus dem eigenen Kopf (Regel 5).
    """
    if "${" not in rule.sql:
        return rule.sql
    sql = _substitute_parameters(rule)
    if _WINDOW_RE.search(sql):
        if ctx.item_window_from is None:
            raise ExecutionError(
                f"{rule.id}: ${{scope.item_window_from}} steht im SQL, aber der Lauf kennt "
                "keinen Fensterbeginn – er enthaelt keinen Posten. Ohne Fenster ist "
                "'angelegt vor Fensterbeginn' nicht entscheidbar."
            )
        sql = _WINDOW_RE.sub(f"DATE '{ctx.item_window_from.isoformat()}'", sql)
    if _DATA_AS_OF_RE.search(sql):
        sql = _DATA_AS_OF_RE.sub(f"DATE '{ctx.data_as_of}'", sql)
    if VAT_PATTERN_PLACEHOLDER_RE.search(sql):
        patterns = ctx.vat_patterns or _default_vat_patterns()
        sql = VAT_PATTERN_PLACEHOLDER_RE.sub(lambda _: patterns.rows(), sql)
    if PLACEHOLDER_TERMS_RE.search(sql):
        terms = ctx.placeholder_terms or _default_placeholder_terms()
        literal = "'" + terms.pattern().replace("'", "''") + "'"
        sql = PLACEHOLDER_TERMS_RE.sub(lambda _: literal, sql)
    if "${" not in sql:
        return sql
    types = ctx.doc_types or _default_doc_types()
    try:
        return substitute(sql, types, rule.id)
    except DictionaryError as exc:
        raise ExecutionError(str(exc)) from exc


def missing_tables(con: duckdb.DuckDBPyConnection, rule: Rule) -> list[str]:
    """Tabellen aus ``requires_tables``, die es in der Verbindung nicht gibt."""
    rows = con.execute("SELECT table_name FROM duckdb_tables()").fetchall()
    known = {row[0] for row in rows}
    return [table for table in rule.requires_tables if table not in known]


def _table_exists(con: duckdb.DuckDBPyConnection, table: str) -> bool:
    rows = con.execute(
        "SELECT count(*) FROM duckdb_tables() WHERE table_name = ?", [table]
    ).fetchone()
    return bool(rows and rows[0])


def _amount_text(value: Any, rule_id: str, label: str) -> str | None:
    """Betrag als Text mit zwei Dezimalen – nie ueber float (Regel 2, D-026)."""
    if value is None:
        return None
    if isinstance(value, float):
        raise ExecutionError(
            f"{rule_id}: {label} ist float. Betraege muessen DECIMAL(15,2) sein (Regel 2)."
        )
    if not isinstance(value, Decimal):
        raise ExecutionError(f"{rule_id}: {label} ist {type(value).__name__}, erwartet DECIMAL.")
    if -value.as_tuple().exponent > 2:
        raise ExecutionError(
            f"{rule_id}: {label} hat mehr als zwei Nachkommastellen. "
            "Runden gehoert in die Regel, nicht in die Engine."
        )
    return f"{value:.2f}"


def _date_text(value: Any, rule_id: str, label: str) -> str | None:
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raise ExecutionError(f"{rule_id}: {label} ist {type(value).__name__}, erwartet DATE oder Text.")


def _decode_json(value: Any, rule_id: str, column: str) -> Any:
    if value is None or isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise ExecutionError(f"{rule_id}: Spalte {column} ist kein gueltiges JSON.") from exc
    raise ExecutionError(f"{rule_id}: Spalte {column} ist {type(value).__name__}, erwartet JSON.")


def _fill(text: str, params: dict[str, Any], rule_id: str, field: str) -> str:
    """Fuellt {params}-Platzhalter. Ein fehlender Platzhalter ist ein Fehler."""
    try:
        return text.format(**params)
    except KeyError as exc:
        raise ExecutionError(
            f"{rule_id}: Platzhalter {exc} in '{field}' fehlt in der Spalte params."
        ) from exc
    except (IndexError, ValueError) as exc:
        raise ExecutionError(
            f"{rule_id}: '{field}' enthaelt eine ungueltige Platzhalter-Angabe ({exc})."
        ) from exc


def house_currency(con: duckdb.DuckDBPyConnection) -> str | None:
    """Die eine Hauswaehrung im Scope des Laufs, oder None ohne ``bp_relevance``.

    V1 rechnet nicht um (D-030): Relevanzbetraege stehen in Hauswaehrung. Mehrere
    Hauswaehrungen im selben Lauf waeren stillschweigend unvergleichbare Betraege –
    dann bricht der Lauf ab. Umrechnung ueber TCURR ist V2.

    Die Quelle der Waehrung ist ``company_code`` aus T001 (D-083); diese Pruefung hier
    liegt hinter der Relevanzstufe und sieht, was tatsaechlich ins Finding laeuft.
    Die Meldung steht in ``relevance.py``, damit es sie nur einmal gibt.
    """
    if not _table_exists(con, "bp_relevance"):
        return None
    rows = con.execute(
        "SELECT DISTINCT currency FROM bp_relevance WHERE currency IS NOT NULL ORDER BY currency"
    ).fetchall()
    currencies = [row[0] for row in rows]
    if len(currencies) > 1:
        raise ExecutionError(multiple_currencies_message(currencies))
    return currencies[0] if currencies else None


def _relevance_by_bp(
    con: duckdb.DuckDBPyConnection, bp_keys: list[str], rule_id: str
) -> dict[str, dict[str, Any]]:
    """Relevanz je BP aus ``bp_relevance``; leer, wenn die Tabelle fehlt."""
    if not bp_keys or not _table_exists(con, "bp_relevance"):
        return {}
    house_currency(con)
    placeholders = ", ".join("?" for _ in bp_keys)
    rows = con.execute(
        "SELECT bp_key, open_items_local, volume_12m_local, currency, last_activity_on "
        f"FROM bp_relevance WHERE bp_key IN ({placeholders})",
        bp_keys,
    ).fetchall()
    return {
        row[0]: {
            "open_items": _amount_text(row[1], rule_id, "bp_relevance.open_items_local"),
            "volume_12m": _amount_text(row[2], rule_id, "bp_relevance.volume_12m_local"),
            "currency": row[3],
            "last_activity_on": _date_text(row[4], rule_id, "bp_relevance.last_activity_on"),
        }
        for row in rows
    }


def _check_contract(columns: list[str], rule: Rule) -> None:
    """Prueft den Ausgabe-Vertrag. Unbekannte Spalte = Fehler mit Namen (Regel 4)."""
    missing = [column for column in REQUIRED_COLUMNS if column not in columns]
    if missing:
        raise ExecutionError(f"{rule.id}: Pflichtspalten fehlen im SQL-Ergebnis: {missing}")
    allowed = set(REQUIRED_COLUMNS) | set(OPTIONAL_COLUMNS)
    unknown = sorted(set(columns) - allowed)
    if unknown:
        raise ExecutionError(f"{rule.id}: unbekannte Spalten im SQL-Ergebnis: {unknown}")
    duplicates = sorted({column for column in columns if columns.count(column) > 1})
    if duplicates:
        raise ExecutionError(f"{rule.id}: Spalten mehrfach im SQL-Ergebnis: {duplicates}")


def _display_names_by_bp(
    con: duckdb.DuckDBPyConnection, bp_keys: list[str]
) -> dict[str, str]:
    """``bp_key -> "Name, Ort"`` aus ``business_partner`` (D-185).

    Zentral hier und nicht je Regel: der Anzeigename haengt am Geschaeftspartner, nicht an
    der Frage, die eine Regel stellt – und 14 Regeln, die dieselbe Zeile selbst bauen,
    wuerden 14 Schreibweisen liefern. Format wie in ``logic/examples/findings/``:
    ``"Müller Maschinenbau GmbH, Augsburg"``. Fehlt eines der beiden Felder, steht das
    andere allein; fehlen beide, bleibt das Feld weg – ein Komma ohne Namen ist kein Name.

    Der Wert steht ausschliesslich im Finding. Er geht **nicht** in die ``finding_id`` ein
    (``ID_COLUMNS``) und nicht in Report, Hinweise oder Logs (Regel 8).
    """
    if not bp_keys or not _table_exists(con, "business_partner"):
        return {}
    placeholders = ", ".join("?" for _ in bp_keys)
    rows = con.execute(
        "SELECT bp_key, name1, city FROM business_partner "
        f"WHERE bp_key IN ({placeholders})",
        bp_keys,
    ).fetchall()
    namen: dict[str, str] = {}
    for bp_key, name1, city in rows:
        teile = [teil.strip() for teil in (name1, city) if teil and teil.strip()]
        if teile:
            namen[bp_key] = ", ".join(teile)
    return namen


def _build_entity(
    row: dict[str, Any], rule: Rule, display_name: str | None = None
) -> dict[str, Any]:
    entity: dict[str, Any] = {"bp_key": row["bp_key"], "role": row["role"]}
    if row.get("company_code") is not None:
        entity["company_code"] = row["company_code"]
    if display_name:
        entity["display_name"] = display_name
    related = _decode_json(row.get("related_bp_keys"), rule.id, "related_bp_keys")
    if related:
        entity["related_bp_keys"] = related
    documents = _decode_json(row.get("documents"), rule.id, "documents")
    if documents:
        entity["documents"] = documents
    # Der Feld-fuer-Feld-Vergleich mehrerer Konten (D-069 Punkt 3). Angelegt fuer
    # Dubletten, aber ausdruecklich nicht darauf eingeschraenkt: AP-CON-001 ist
    # `consistency` und braucht denselben Vergleich (D-069 Punkt 4).
    records = _decode_json(row.get("records"), rule.id, "records")
    if records:
        entity["records"] = records
    return entity


def _build_proposed(row: dict[str, Any], rule: Rule) -> dict[str, Any] | None:
    """Das Soll – oder ``None``, wenn es keines gibt (D-186).

    Ein Soll ist ein Wert (``proposed_value``), eine aufbereitete Entscheidung
    (``options``) oder eine Handlung, die in kein Feld passt (``proposed_display``).
    Ein ``proposed``, das **nur** eine Quellenlage traegt, ist keines von beidem: es
    erklaert, warum es kein Soll gibt, und sieht in jeder Ansicht aus wie ein leerer
    Vorschlag. Diese Form bricht den Lauf ab (Regel 6) – der Satz gehoert nach
    ``remediation`` oder ``why``.
    """
    options = _decode_json(row.get("options"), rule.id, "options")
    traegt_soll = row.get("proposed_value") is not None or bool(options) or (
        row.get("proposed_display") is not None
    )
    if not traegt_soll:
        if row.get("source_summary") is not None:
            raise InvalidFindingError(
                f"{rule.id}: proposed traegt nur eine Quellenlage und kein Soll "
                f"(bp_key {row['bp_key']}). Ohne Soll gehoert kein proposed ins Finding; "
                "der erklaerende Satz gehoert nach remediation oder why (D-186)."
            )
        return None
    proposed: dict[str, Any] = {
        "value": row.get("proposed_value"),
        "display": row.get("proposed_display"),
        "source_summary": row.get("source_summary"),
    }
    if options:
        proposed["options"] = options
    return proposed


def _build_impact(row: dict[str, Any], rule: Rule) -> dict[str, Any] | None:
    amount = _amount_text(row.get("impact_amount"), rule.id, "impact_amount")
    if amount is None:
        return None
    impact: dict[str, Any] = {
        "amount": amount,
        "currency": row.get("impact_currency"),
        "formula": row.get("impact_formula"),
    }
    if row.get("netted_against") is not None:
        impact["netted_against"] = row["netted_against"]
    return impact


def _build_finding(
    row: dict[str, Any],
    rule: Rule,
    ctx: RunContext,
    relevance: dict[str, dict[str, Any]],
    display_names: dict[str, str] | None = None,
) -> dict[str, Any]:
    display_names = display_names or {}
    params = _decode_json(row.get("params"), rule.id, "params") or {}
    if not isinstance(params, dict):
        raise ExecutionError(f"{rule.id}: Spalte params ist kein JSON-Objekt.")

    finding: dict[str, Any] = {
        "finding_id": finding_id_for(rule.id, row),
        "run_id": ctx.run_id,
        "rule_id": rule.id,
        "rule_version": rule.version,
        "engine_version": ctx.engine_version,
        "pack_version": ctx.pack_version,
        "side": rule.side,
        "category": rule.category,
        "severity": rule.severity,
        "damage_class": rule.damage_class,
        "tier": row.get("tier") or rule.default_tier,
        "action_type": row.get("action_type") or rule.default_action_type,
    }

    finding["title"] = _fill(rule.title, params, rule.id, "title")
    finding["entity"] = _build_entity(row, rule, display_names.get(row["bp_key"]))

    bp_relevance = relevance.get(row["bp_key"])
    if bp_relevance:
        finding["relevance"] = bp_relevance

    finding["current"] = {
        "source_table": row["source_table"],
        "source_field": row["source_field"],
        "value": row["current_value"],
        "display": row.get("current_display"),
    }

    proposed = _build_proposed(row, rule)
    if proposed is not None:
        finding["proposed"] = proposed

    evidence = _decode_json(row.get("evidence"), rule.id, "evidence")
    if evidence:
        finding["evidence"] = evidence

    impact = _build_impact(row, rule)
    if impact is not None:
        finding["impact_eur"] = impact

    finding["why"] = _fill(rule.why, params, rule.id, "why")
    finding["if_wrong"] = _fill(rule.if_wrong, params, rule.id, "if_wrong")
    finding["remediation"] = rule.remediation
    finding["status"] = "open"
    finding["data_as_of"] = ctx.data_as_of
    finding["created_at"] = ctx.created_at
    # Eine getroffene Entscheidung setzt den Status – das Finding entsteht trotzdem und
    # verschwindet nie stumm (Regel 4, D-088).
    return apply_decision(finding, ctx.decisions)


def execute_rule_rows(
    con: duckdb.DuckDBPyConnection, rule: Rule, ctx: RunContext
) -> list[tuple[dict[str, Any], str | None]]:
    """Wie ``execute_rule``, liefert je Finding zusaetzlich seinen ``finding_key``.

    Der ``finding_key`` geht sonst nur in die ``finding_id`` ein und ist aus dem fertigen
    Finding nicht mehr herauszulesen. Der Regressionsvergleich braucht ihn aber als Teil
    seines Vergleichsschluessels (D-068) -- und er darf ihn nicht aus ``entity.documents``
    zurueckrechnen, denn was in den Schluessel gehoert, entscheidet jede Regel selbst.
    """
    absent = missing_tables(con, rule)
    if absent:
        raise ExecutionError(f"{rule.id}: benoetigte Tabellen fehlen: {absent}")

    ensure_rule_macros(con)
    try:
        cursor = con.execute(rule_sql(rule, ctx))
    except duckdb.Error as exc:
        raise ExecutionError(f"{rule.id}: SQL-Fehler ({type(exc).__name__}): {exc}") from exc

    columns = [description[0] for description in cursor.description]
    _check_contract(columns, rule)
    rows = [dict(zip(columns, values, strict=True)) for values in cursor.fetchall()]

    bp_keys = [row["bp_key"] for row in rows]
    relevance = _relevance_by_bp(con, bp_keys, rule.id)
    display_names = _display_names_by_bp(con, bp_keys)

    findings: list[tuple[dict[str, Any], str | None]] = []
    seen: dict[str, int] = {}
    for position, row in enumerate(rows):
        finding = _build_finding(row, rule, ctx, relevance, display_names)
        finding_id = finding["finding_id"]
        if finding_id in seen:
            raise ExecutionError(
                f"{rule.id}: finding_id {finding_id} kollidiert (Zeilen {seen[finding_id]} "
                f"und {position}). Der Regel fehlt eine finding_key-Spalte."
            )
        seen[finding_id] = position

        errors = validate_finding(finding)
        if errors:
            joined = "\n    ".join(errors)
            raise InvalidFindingError(
                f"{rule.id}: Finding ist nicht schema-valide:\n    {joined}"
            )
        findings.append((finding, row.get("finding_key")))
    return findings


def execute_rule(
    con: duckdb.DuckDBPyConnection, rule: Rule, ctx: RunContext
) -> list[dict[str, Any]]:
    """Fuehrt eine Regel aus und liefert die geprueften Findings in SQL-Reihenfolge."""
    return [finding for finding, _ in execute_rule_rows(con, rule, ctx)]
