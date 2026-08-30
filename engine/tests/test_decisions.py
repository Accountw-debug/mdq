"""Entscheidungsgedaechtnis: Whitelist wirkt, nichts verschwindet stumm.

Geprueft wird beides: dass eine getroffene Entscheidung den Status des Findings setzt –
und dass das Finding trotzdem entsteht (Regel 4). Dazu die strengen Faelle: unbekannter
Grund, doppelte ID, fehlendes Pflichtfeld, ein Eintrag, dessen `rule_id`/`bp_key` nicht
zum Finding passt, und der verwaiste Eintrag als Hinweis.

Alle Schluessel hier sind erfunden; Namen oder Adressen kommen nicht vor (Regel 8).
"""

from datetime import datetime
from pathlib import Path

import pytest

from mdq.decisions import (
    REASON_STATUS,
    DecisionError,
    DecisionMemory,
    apply_decision,
    find_decisions,
    load_decisions,
    parse_decisions,
    store_decisions,
)
from mdq.executor import RunContext, execute_rule
from mdq.report import DecisionSummary
from mdq.rules import parse_rule

FINDING_ID = "F-000000000001"

DATEI = """version: "0.1"
decisions:
  - finding_id: {finding_id}
    rule_id: AR-VAL-001
    bp_key: C:0000000001
    decided_by: pruefer1
    decided_at: 2026-08-20T10:00:00
    reason_code: data_correct
    reason: "USt-IdNr. wurde beim Kunden geprueft und ist richtig."
"""


def schreibe(tmp_path: Path, text: str, name: str = "decisions.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def lade(tmp_path: Path, text: str) -> DecisionMemory:
    return load_decisions(schreibe(tmp_path, text))


# --- Die Datei -------------------------------------------------------------------------


def test_eintrag_wird_gelesen(tmp_path):
    memory = lade(tmp_path, DATEI.format(finding_id=FINDING_ID))
    decision = memory.get(FINDING_ID)
    assert decision is not None
    assert decision.rule_id == "AR-VAL-001"
    assert decision.bp_key == "C:0000000001"
    assert decision.decided_at == datetime.fromisoformat("2026-08-20T10:00:00")
    assert decision.status == "rejected"


def test_datum_ohne_uhrzeit_gilt_als_mitternacht(tmp_path):
    text = DATEI.format(finding_id=FINDING_ID).replace("2026-08-20T10:00:00", "2026-08-20")
    assert lade(tmp_path, text).get(FINDING_ID).decided_at == datetime.fromisoformat(
        "2026-08-20T00:00:00"
    )


def test_leere_datei_ist_ein_leeres_gedaechtnis(tmp_path):
    assert len(lade(tmp_path, 'version: "0.1"\ndecisions: []\n')) == 0


def test_unbekannter_grund_wird_mit_zeilennummer_gemeldet(tmp_path):
    text = DATEI.format(finding_id=FINDING_ID).replace("data_correct", "weil_ich_es_sage")
    with pytest.raises(DecisionError) as excinfo:
        lade(tmp_path, text)
    message = str(excinfo.value)
    assert "weil_ich_es_sage" in message
    assert "Zeile 3" in message
    assert "accepted_risk" in message  # die erlaubten Gruende stehen in der Meldung


def test_fehlendes_pflichtfeld_wird_gemeldet(tmp_path):
    text = DATEI.format(finding_id=FINDING_ID).replace("    decided_by: pruefer1\n", "")
    with pytest.raises(DecisionError) as excinfo:
        lade(tmp_path, text)
    assert "decided_by" in str(excinfo.value)


def test_unbekanntes_feld_wird_gemeldet(tmp_path):
    text = DATEI.format(finding_id=FINDING_ID) + "    schwere: hoch\n"
    with pytest.raises(DecisionError) as excinfo:
        lade(tmp_path, text)
    assert "schwere" in str(excinfo.value)


def test_dieselbe_finding_id_zweimal_ist_ein_fehler(tmp_path):
    text = DATEI.format(finding_id=FINDING_ID) + DATEI.format(finding_id=FINDING_ID).split(
        "decisions:\n"
    )[1]
    with pytest.raises(DecisionError) as excinfo:
        lade(tmp_path, text)
    assert "mehrfach" in str(excinfo.value)


def test_alle_probleme_werden_gemeinsam_gemeldet(tmp_path):
    text = (
        'version: "0.1"\n'
        "decisions:\n"
        "  - finding_id: F-1\n"
        "    rule_id: AR-VAL-001\n"
        "    bp_key: C:0000000001\n"
        "    decided_by: pruefer1\n"
        "    decided_at: 2026-08-20\n"
        "    reason_code: unbekannt\n"
        '    reason: "x"\n'
        "  - finding_id: F-2\n"
        "    rule_id: AR-VAL-001\n"
        "    bp_key: C:0000000002\n"
        "    decided_by: pruefer1\n"
        "    decided_at: gestern\n"
        "    reason_code: data_correct\n"
        '    reason: "y"\n'
    )
    with pytest.raises(DecisionError) as excinfo:
        lade(tmp_path, text)
    message = str(excinfo.value)
    assert "unbekannt" in message and "decided_at" in message


def test_jeder_grund_bildet_auf_einen_status_des_schemas_ab():
    """Kein neuer Statuswert (D-089): beide Ziele stehen im Finding-Schema."""
    assert set(REASON_STATUS.values()) == {"rejected", "accepted_risk"}
    assert REASON_STATUS["accepted_risk"] == "accepted_risk"


# --- Der Pfad --------------------------------------------------------------------------


def test_vorgabedatei_wird_gefunden(tmp_path):
    schreibe(tmp_path, DATEI.format(finding_id=FINDING_ID))
    assert find_decisions(tmp_path) == tmp_path / "decisions.yaml"


def test_ohne_datei_gibt_es_kein_gedaechtnis(tmp_path):
    assert find_decisions(tmp_path) is None


def test_ausdruecklich_genannte_datei_muss_existieren(tmp_path):
    with pytest.raises(DecisionError) as excinfo:
        find_decisions(tmp_path, tmp_path / "fehlt.yaml")
    assert "fehlt.yaml" in str(excinfo.value)


# --- Die Wirkung auf ein Finding -------------------------------------------------------


RULE_TEXT = """/* ---
id: AR-VAL-001
version: "1.0"
title: "Testregel Gedaechtnis"
side: AR
category: validity
severity: medium
damage_class: 3
default_tier: C
default_action_type: review
requires_tables: [business_partner]
plain_logic: >
  Trifft jeden Partner – Testregel fuer das Entscheidungsgedaechtnis.
why: >
  Fachlich ohne Bedeutung, reiner Testfall.
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
SELECT bp_key, role, 'KNA1' AS source_table, 'STCEG' AS source_field,
       NULL AS current_value
FROM business_partner ORDER BY bp_key;
"""


@pytest.fixture
def db_mit_partner(canonical_db):
    canonical_db.execute(
        "INSERT INTO business_partner (bp_key, role, source_id) "
        "VALUES ('C:0000000001', 'CUSTOMER', '0000000001')"
    )
    return canonical_db


def rule():
    return parse_rule(RULE_TEXT, Path("AR-VAL-001.rule.sql"))


def context(memory: DecisionMemory | None) -> RunContext:
    return RunContext(
        run_id="test-run",
        engine_version="0.1.0",
        pack_version="0.1",
        data_as_of="2026-08-28",
        created_at="2026-08-30T09:15:00Z",
        decisions=memory,
    )


def test_ohne_gedaechtnis_bleibt_das_finding_offen(db_mit_partner):
    findings = execute_rule(db_mit_partner, rule(), context(None))
    assert [f["status"] for f in findings] == ["open"]
    assert "decision" not in findings[0]


def test_entscheidung_setzt_status_und_grund(db_mit_partner, tmp_path):
    offen = execute_rule(db_mit_partner, rule(), context(None))[0]
    memory = lade(tmp_path, DATEI.format(finding_id=offen["finding_id"]))

    findings = execute_rule(db_mit_partner, rule(), context(memory))
    # Das Finding entsteht weiterhin – eine Whitelist unterdrueckt nichts (Regel 4).
    assert len(findings) == 1
    assert findings[0]["status"] == "rejected"
    assert findings[0]["decision"]["reason_code"] == "data_correct"
    assert findings[0]["decision"]["by"] == "pruefer1"
    assert memory.applied == {offen["finding_id"]}


def test_accepted_risk_behaelt_seinen_namen(db_mit_partner, tmp_path):
    offen = execute_rule(db_mit_partner, rule(), context(None))[0]
    text = DATEI.format(finding_id=offen["finding_id"]).replace(
        "data_correct", "accepted_risk"
    )
    findings = execute_rule(db_mit_partner, rule(), context(lade(tmp_path, text)))
    assert findings[0]["status"] == "accepted_risk"


def test_eintrag_mit_falscher_regel_ist_ein_fehler(db_mit_partner, tmp_path):
    """Dieselbe finding_id bei anderer Regel heisst: der Eintrag ist veraltet."""
    offen = execute_rule(db_mit_partner, rule(), context(None))[0]
    text = DATEI.format(finding_id=offen["finding_id"]).replace("AR-VAL-001", "AR-VAL-999")
    with pytest.raises(DecisionError) as excinfo:
        execute_rule(db_mit_partner, rule(), context(lade(tmp_path, text)))
    assert "AR-VAL-999" in str(excinfo.value)


def test_eintrag_mit_falschem_konto_ist_ein_fehler(db_mit_partner, tmp_path):
    offen = execute_rule(db_mit_partner, rule(), context(None))[0]
    text = DATEI.format(finding_id=offen["finding_id"]).replace(
        "C:0000000001", "C:0000000099"
    )
    with pytest.raises(DecisionError) as excinfo:
        execute_rule(db_mit_partner, rule(), context(lade(tmp_path, text)))
    assert "C:0000000099" in str(excinfo.value)


def test_verwaister_eintrag_ist_ein_hinweis_kein_fehler(db_mit_partner, tmp_path):
    """Ein Eintrag ohne passendes Finding faellt auf, bricht aber nichts ab."""
    memory = lade(tmp_path, DATEI.format(finding_id="F-gibtesnicht"))
    execute_rule(db_mit_partner, rule(), context(memory))
    assert [d.finding_id for d in memory.orphans] == ["F-gibtesnicht"]

    summary = DecisionSummary.of(memory)
    assert summary.loaded == 1 and summary.applied == 0
    assert summary.warnings and "F-gibtesnicht" in summary.warnings[0]


def test_ohne_regellauf_gilt_kein_eintrag_als_verwaist(tmp_path):
    """`mdq load` fuehrt keine Regeln aus – 'verwaist' waere dort ohne Aussage."""
    memory = lade(tmp_path, DATEI.format(finding_id=FINDING_ID))
    summary = DecisionSummary.of(memory, rules_executed=False)
    assert summary.orphans == () and summary.warnings == []


def test_apply_decision_ohne_gedaechtnis_laesst_das_finding_unberuehrt(minimal_finding):
    assert apply_decision(dict(minimal_finding), None) == minimal_finding


# --- Die kanonische Tabelle ------------------------------------------------------------


def test_gedaechtnis_steht_in_der_kanonischen_tabelle(canonical_db, tmp_path):
    memory = lade(tmp_path, DATEI.format(finding_id=FINDING_ID))
    assert store_decisions(canonical_db, memory) == 1
    row = canonical_db.execute(
        "SELECT finding_id, rule_id, bp_key, decided_by, reason_code FROM decision_memory"
    ).fetchone()
    assert row == (FINDING_ID, "AR-VAL-001", "C:0000000001", "pruefer1", "data_correct")


def test_zweimal_schreiben_gibt_dieselbe_tabelle(canonical_db, tmp_path):
    """Regel 9: ein zweiter Lauf ueber dieselbe Datei ergibt dieselben Zeilen."""
    memory = lade(tmp_path, DATEI.format(finding_id=FINDING_ID))
    store_decisions(canonical_db, memory)
    first = canonical_db.execute("SELECT * FROM decision_memory ORDER BY finding_id").fetchall()
    store_decisions(canonical_db, memory)
    second = canonical_db.execute("SELECT * FROM decision_memory ORDER BY finding_id").fetchall()
    assert first == second


def test_datei_ohne_objekt_wird_abgewiesen(tmp_path):
    with pytest.raises(DecisionError):
        parse_decisions(["kein Objekt"], tmp_path / "decisions.yaml")
