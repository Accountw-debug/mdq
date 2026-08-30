"""Ausfuehrung einer Regel gegen DuckDB und Bau der Findings.

Der Ausgabe-Vertrag des SQL steht in ``logic/rules/README.md``. Alles, was die Regel nicht
liefert, ergaenzt diese Datei: Defaults aus dem Regelkopf, Versionen und Zeitpunkt aus dem
``RunContext``, Relevanz aus ``bp_relevance``. Jedes Finding wird gegen das Schema
validiert (CLAUDE.md, Regel 6).
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from functools import cache
from typing import Any

import duckdb

from mdq.decisions import DecisionMemory, apply_decision
from mdq.dictionaries import DictionaryError, DocumentTypes, load_document_types, substitute
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
JSON_COLUMNS = ("options", "evidence", "related_bp_keys", "documents", "params")

#: Felder des Regelkopfes, in denen {params}-Platzhalter gefuellt werden
TEMPLATED_FIELDS = ("title", "why", "if_wrong")


class ExecutionError(RuntimeError):
    """Die Regel konnte nicht ausgefuehrt werden oder verletzt den Ausgabe-Vertrag."""


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
def _default_doc_types() -> DocumentTypes:
    """Das Woerterbuch aus ``logic/`` – einmal gelesen, nicht je Regel neu."""
    return load_document_types()


def rule_sql(rule: Rule, ctx: RunContext) -> str:
    """Das auszufuehrende SQL: Belegartenlisten eingesetzt, sonst unveraendert (D-084).

    Die Regel liest damit weiterhin nur das kanonische Schema; die Liste kommt als
    Parameter von der Engine und steht nicht zweimal im Repo (Regel 5).
    """
    if "${" not in rule.sql:
        return rule.sql
    types = ctx.doc_types or _default_doc_types()
    try:
        return substitute(rule.sql, types, rule.id)
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


def _build_entity(row: dict[str, Any], rule: Rule) -> dict[str, Any]:
    entity: dict[str, Any] = {"bp_key": row["bp_key"], "role": row["role"]}
    if row.get("company_code") is not None:
        entity["company_code"] = row["company_code"]
    related = _decode_json(row.get("related_bp_keys"), rule.id, "related_bp_keys")
    if related:
        entity["related_bp_keys"] = related
    documents = _decode_json(row.get("documents"), rule.id, "documents")
    if documents:
        entity["documents"] = documents
    return entity


def _build_proposed(row: dict[str, Any], rule: Rule) -> dict[str, Any] | None:
    options = _decode_json(row.get("options"), rule.id, "options")
    has_content = any(
        row.get(column) is not None for column in ("proposed_value", "source_summary")
    ) or bool(options)
    if not has_content:
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
) -> dict[str, Any]:
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
    finding["entity"] = _build_entity(row, rule)

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

    try:
        cursor = con.execute(rule_sql(rule, ctx))
    except duckdb.Error as exc:
        raise ExecutionError(f"{rule.id}: SQL-Fehler ({type(exc).__name__}): {exc}") from exc

    columns = [description[0] for description in cursor.description]
    _check_contract(columns, rule)
    rows = [dict(zip(columns, values, strict=True)) for values in cursor.fetchall()]

    relevance = _relevance_by_bp(con, [row["bp_key"] for row in rows], rule.id)

    findings: list[tuple[dict[str, Any], str | None]] = []
    seen: dict[str, int] = {}
    for position, row in enumerate(rows):
        finding = _build_finding(row, rule, ctx, relevance)
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
            raise ExecutionError(f"{rule.id}: Finding ist nicht schema-valide:\n    {joined}")
        findings.append((finding, row.get("finding_key")))
    return findings


def execute_rule(
    con: duckdb.DuckDBPyConnection, rule: Rule, ctx: RunContext
) -> list[dict[str, Any]]:
    """Fuehrt eine Regel aus und liefert die geprueften Findings in SQL-Reihenfolge."""
    return [finding for finding, _ in execute_rule_rows(con, rule, ctx)]
