"""Gemeinsame Fixtures der Engine-Tests."""

from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest

from mdq import CANONICAL_SCHEMA, DEMO_MANDANT_DIR, LOGIC_DIR, PROJECT_ROOT, RULES_DIR
from mdq.demo import DEFAULT_SEED
from mdq.demo.generate import build_client
from mdq.demo.generate import generate as generate_demo
from mdq.executor import RunContext
from mdq.regression import actual_from_findings, compare, load_expected
from mdq.rules import load_rules
from mdq.run import RunOptions, execute_run


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
        "title": "Testfall Schema-Validierung",
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


@pytest.fixture(scope="session")
def demo_client(tmp_path_factory):
    """Der ausgelieferte Demo-Mandant: Basis plus die Defekte aus `defects.yaml`."""
    out = tmp_path_factory.mktemp("demo_mandant")
    manifest = generate_demo(out, DEFAULT_SEED)
    return out, manifest


@pytest.fixture(scope="session")
def demo_base_client(tmp_path_factory):
    """Der *defektfreie* Basis-Mandant.

    Auf ihm darf keine Regel greifen (D-045); `test_demo_base.py` prueft genau das. Die
    Defekte verletzen diese Invarianten absichtlich, deshalb braucht der Basis-Test einen
    eigenen Mandanten – erzeugt mit einer ausdruecklich leeren Defektliste.
    """
    out = tmp_path_factory.mktemp("demo_mandant_base")
    manifest = generate_demo(out, DEFAULT_SEED, ())
    return out, manifest


@pytest.fixture(scope="session")
def demo_expected():
    """Die erwarteten Findings des ausgelieferten Demo-Mandanten."""
    return build_client(DEFAULT_SEED).expected


def demo_rows(path, table: str) -> list[dict[str, str]]:
    """Zeilen einer Exportdatei als Liste von Spalte -> Wert."""
    lines = (path / f"{table}.txt").read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t")
    return [dict(zip(header, line.split("\t"), strict=True)) for line in lines[1:]]


#: Regeln, die `expected_findings.yaml` erwartet und die es als Datei noch nicht gibt.
#: Diese Menge ist eine Erklaerung, keine Erwartung: sie sagt, welche Regeln gebaut sind
#: – nicht, ob sie das Richtige finden (das pruefen die drei Fehlertoepfe der Regression).
#: Ein Regelpaket entfernt seine IDs hier im selben Commit; am Ende von Sprint 3 muss
#: genau {AR-DUP-001, AP-DUP-001} uebrig sein (D-100). Verschwindet eine Regeldatei
#: versehentlich, faellt die Regression rot aus statt still durchzugehen.
NOT_YET_BUILT = {
    "AP-COM-003",
    "AP-CON-001",
    "AP-DUP-001",
    "AP-HYG-001",
    "AP-LEA-002",
    "AP-VAL-002",
    "AP-VAL-003",
    "AR-DUP-001",
    "AR-LEA-001",
    "CROSS-DUP-001",
}


# --- Der Lauf auf dem eingecheckten Demo-Mandanten ------------------------------------


@pytest.fixture(scope="session")
def regression_run(tmp_path_factory):
    """Ein Lauf auf `testdata/demo_mandant` – die Eingabe aus SPRINT-3.md, Aufgabe 5.

    Bewusst der eingecheckte Ordner und nicht die neu erzeugte Fixture: die Regeln sehen
    im Repo genau diese Dateien. Dass sie dem Generator entsprechen, haelt
    `test_demo_output.test_repo_copy_matches_the_generator` fest. Sitzungsweit, weil der
    Lauf einige Sekunden braucht und sowohl die Regression als auch die Regeltests
    dasselbe Ergebnis pruefen.
    """
    return execute_run(
        RunOptions(
            input_dir=DEMO_MANDANT_DIR,
            out_dir=tmp_path_factory.mktemp("regression"),
            created_at="2026-08-31T08:00:00Z",
        )
    )


@pytest.fixture(scope="session")
def comparison(regression_run):
    """Erwartung und Lauf, verglichen ueber `regression.py`."""
    return compare(
        load_expected(),
        actual_from_findings(regression_run.finding_rows),
        {rule.id: rule.version for rule in load_rules(RULES_DIR)},
    )


def findings_of(run, rule_id: str) -> list[dict]:
    """Die Findings einer Regel aus einem Lauf, in Laufreihenfolge."""
    return [finding for finding in run.findings if finding["rule_id"] == rule_id]
