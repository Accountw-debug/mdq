"""Gemeinsame Fixtures der Engine-Tests."""

from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest

from mdq import CANONICAL_SCHEMA, LOGIC_DIR, PROJECT_ROOT
from mdq.executor import RunContext


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Wurzel des Repos."""
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def logic_dir() -> Path:
    """Verzeichnis logic/ – Schema, Regeln, Mappings, Woerterbuecher."""
    return LOGIC_DIR


@pytest.fixture(scope="session")
def example_findings_dir() -> Path:
    """Verzeichnis der fachlichen Beispiel-Findings – zugleich Spec fuer UI und Engine."""
    return LOGIC_DIR / "examples" / "findings"


@pytest.fixture
def minimal_finding() -> dict:
    """Kleinstes vollstaendig valides Finding.

    Bewusst im Testcode und nicht als Datei: `logic/examples/findings/` ist Victors
    fachliche Spec und darf keine kuenstlichen Testartefakte enthalten. Alle Werte sind
    erfunden, es stehen keine Geschaeftspartnerdaten darin (Regel 8).
    """
    return {
        "finding_id": "F-000000000001",
        "run_id": "test-run",
        "rule_id": "AR-VAL-001",
        "rule_version": "1.0",
        "engine_version": "0.1.0",
        "pack_version": "0.1",
        "side": "AR",
        "category": "validity",
        "severity": "medium",
        "damage_class": 3,
        "tier": "C",
        "action_type": "review",
        "entity": {"bp_key": "C:0000000001", "role": "CUSTOMER"},
        "current": {"source_table": "KNA1", "source_field": "STCEG", "value": None},
        "why": "Testfall fuer die Schema-Validierung, fachlich ohne Bedeutung.",
        "if_wrong": "Kein Schaden, reiner Testfall.",
        "remediation": {"sap_transaction": "XD02", "mass_change_eligible": False},
        "status": "open",
        "data_as_of": "2026-08-28",
        "created_at": "2026-08-30T09:15:00Z",
    }


VALID_RULE_TEXT = """/* ---
id: AR-VAL-009
version: "1.0"
title: "Testregel"
side: AR
category: validity
severity: medium
damage_class: 3
default_tier: B
default_action_type: review
requires_tables: [business_partner]
plain_logic: >
  Trifft nie – Testregel fuer den Loader.
why: >
  Ohne Grund kein Finding; dieser Text ist fachlich bedeutungslos.
if_wrong: >
  Kein Schaden, reiner Testfall.
remediation:
  sap_transaction: XD02
  path: null
  field: null
  mass_change_eligible: false
tests:
  hits: ["C:0000000001"]
  no_hits: ["C:0000000002"]
  edge: []
--- */
SELECT bp_key, role FROM business_partner WHERE FALSE ORDER BY bp_key;
"""


@pytest.fixture
def run_context() -> RunContext:
    """Feste Laufkopfdaten – nie datetime.now(), sonst ist Determinismus nicht haltbar."""
    return RunContext(
        run_id="test-run",
        engine_version="0.1.0",
        pack_version="0.1",
        data_as_of="2026-08-28",
        created_at="2026-08-30T09:15:00Z",
    )


@pytest.fixture
def valid_rule_text() -> str:
    """Minimaler gueltiger Regeltext – Basis fuer Mutationen in den Loader-Tests."""
    return VALID_RULE_TEXT


@pytest.fixture
def canonical_db() -> Iterator[duckdb.DuckDBPyConnection]:
    """DuckDB im Speicher mit geladenem kanonischen Schema.

    Bewusst je Test frisch: Tests duerfen sich nicht gegenseitig beeinflussen,
    sonst ist die Reihenfolge der Findings nicht mehr deterministisch.
    """
    con = duckdb.connect(":memory:")
    try:
        con.execute(CANONICAL_SCHEMA.read_text(encoding="utf-8"))
        yield con
    finally:
        con.close()
