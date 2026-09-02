"""Regel-Ausfuehrung: Ausgabe-Vertrag, finding_id, Determinismus, Schema-Validitaet.

Alle Testdaten sind erfunden. Es stehen keine Geschaeftspartnerdaten in dieser Datei
(CLAUDE.md, Regel 8) – nur technische Schluessel und Platzhalternamen.
"""

import dataclasses
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from mdq.dictionaries import parse_document_types
from mdq.executor import (
    ID_COLUMNS,
    ExecutionError,
    InvalidFindingError,
    RunContext,
    _display_names_by_bp,
    execute_rule,
    finding_id_for,
    house_currency,
    missing_tables,
    rule_sql,
)
from mdq.findings import validate_finding
from mdq.rules import load_rules, parse_rule

from .conftest import VALID_RULE_TEXT

RULES = {rule.id: rule for rule in load_rules()}

# --- Testdaten je Beispielregel (erfundene Schluessel) --------------------------------

INSERT_AR_VAL_001 = """
INSERT INTO business_partner (bp_key, role, source_id, country, is_one_time)
VALUES ('C:0000000001','CUSTOMER','0000000001','DE',FALSE);
INSERT INTO bp_tax_id (bp_key, tax_id_type, country, value, value_norm)
VALUES ('C:0000000001','VAT','DE','AT U12345678','ATU12345678');
"""

#: `company_code` (T001) ist Vorbedingung, seit die Regel ihr Waehrungsetikett von dort
#: nimmt und nicht mehr aus der Belegwaehrung der Posten (D-205) - keine Erwartung, die
#: angepasst wurde, sondern eine Tabelle, die die Regel jetzt braucht.
INSERT_AR_CON_002 = """
INSERT INTO company_code (company_code, name, currency, country)
VALUES ('1000','Demo Industrie AG','EUR','DE');
INSERT INTO business_partner (bp_key, role, source_id, country, is_one_time, deletion_flag)
VALUES ('C:0000000002','CUSTOMER','0000000002','DE',FALSE,TRUE);
INSERT INTO bp_company_code (bp_key, company_code) VALUES ('C:0000000002','1000');
INSERT INTO fi_item (item_key,bp_key,company_code,fiscal_year,document_no,line_item,
                     posting_date,currency,amount_doc,amount_local,amount_signed_local,is_open)
VALUES ('1000|2026|1|1','C:0000000002','1000','2026','1','1',DATE '2026-01-05','EUR',
        100.00,100.00,100.00,TRUE);
"""

#: Derselbe Debitor, aber offene Posten in **zwei Belegwaehrungen** desselben
#: Buchungskreises. Die Hauswaehrung ist EUR; die USD-Rechnung traegt ihren DMBTR-Betrag
#: trotzdem in EUR (Glossar "Hauswaehrung"). Bis D-205 zerfiel das in zwei Zeilen mit
#: derselben Identitaet und die finding_id kollidierte.
INSERT_AR_CON_002_ZWEI_WAEHRUNGEN = """
INSERT INTO company_code (company_code, name, currency, country)
VALUES ('1000','Demo Industrie AG','EUR','DE');
INSERT INTO business_partner (bp_key, role, source_id, country, is_one_time, deletion_flag)
VALUES ('C:0000000002','CUSTOMER','0000000002','DE',FALSE,TRUE);
INSERT INTO bp_company_code (bp_key, company_code) VALUES ('C:0000000002','1000');
INSERT INTO fi_item (item_key,bp_key,company_code,fiscal_year,document_no,line_item,
                     posting_date,currency,amount_doc,amount_local,amount_signed_local,is_open)
VALUES
 ('1000|2026|1|1','C:0000000002','1000','2026','1','1',DATE '2026-01-05','EUR',
  100.00,100.00,100.00,TRUE),
 ('1000|2026|2|1','C:0000000002','1000','2026','2','1',DATE '2026-02-05','USD',
  250.00,220.00,220.00,TRUE);
"""

INSERT_AP_LEA_001 = """
INSERT INTO business_partner (bp_key, role, source_id, country, is_one_time)
VALUES ('V:0000000003','VENDOR','0000000003','DE',FALSE);
INSERT INTO fi_item (item_key,bp_key,company_code,fiscal_year,document_no,line_item,
                     posting_date,document_date,doc_type,debit_credit,currency,
                     amount_doc,amount_local,amount_signed_local,reference,reference_norm,is_open)
VALUES
 ('1000|2026|10|1','V:0000000003','1000','2026','10','1',DATE '2026-02-01',DATE '2026-02-01',
  'KR','H','EUR',500.00,500.00,-500.00,'RE-1','RE1',FALSE),
 ('1000|2026|11|1','V:0000000003','1000','2026','11','1',DATE '2026-02-10',DATE '2026-02-10',
  'KR','H','EUR',500.00,500.00,-500.00,'RE 1','RE1',FALSE);
"""

#: Die beiden Zahlungen zu den Rechnungen oben: Belegart KZ, beim Kreditor Soll.
#: Genau daran scheiterte die Regel bis D-082 - sie hielt die Zahlung fuer die Gutschrift.
INSERT_AP_LEA_001_PAYMENTS = """
INSERT INTO fi_item (item_key,bp_key,company_code,fiscal_year,document_no,line_item,
                     posting_date,document_date,doc_type,debit_credit,currency,
                     amount_doc,amount_local,amount_signed_local,is_open)
VALUES
 ('1000|2026|20|1','V:0000000003','1000','2026','20','1',DATE '2026-03-05',DATE '2026-03-05',
  'KZ','S','EUR',500.00,500.00,500.00,FALSE),
 ('1000|2026|21|1','V:0000000003','1000','2026','21','1',DATE '2026-03-12',DATE '2026-03-12',
  'KZ','S','EUR',500.00,500.00,500.00,FALSE);
"""

#: Eine echte Gutschrift in gleicher Hoehe innerhalb von 180 Tagen - sie nettet das Paar.
INSERT_AP_LEA_001_CREDIT_MEMO = """
INSERT INTO fi_item (item_key,bp_key,company_code,fiscal_year,document_no,line_item,
                     posting_date,document_date,doc_type,debit_credit,currency,
                     amount_doc,amount_local,amount_signed_local,is_open)
VALUES ('1000|2026|30|1','V:0000000003','1000','2026','30','1',DATE '2026-04-01',
        DATE '2026-04-01','KG','S','EUR',500.00,500.00,500.00,TRUE);
"""

CASES = [
    ("AR-VAL-001", INSERT_AR_VAL_001),
    ("AR-CON-002", INSERT_AR_CON_002),
    ("AP-LEA-001", INSERT_AP_LEA_001),
]


@pytest.fixture
def db(canonical_db):
    """Kanonisches Schema; Testdaten fuegt der jeweilige Test ein."""
    return canonical_db


def _run(db, rule_id: str, inserts: str, ctx: RunContext) -> list[dict]:
    db.execute(inserts)
    return execute_rule(db, RULES[rule_id], ctx)


# --- Der Spec-Fall: je Regel genau 1 schema-valides Finding ---------------------------


@pytest.mark.parametrize(("rule_id", "inserts"), CASES, ids=[c[0] for c in CASES])
def test_each_rule_yields_one_valid_finding(db, run_context, rule_id, inserts) -> None:
    findings = _run(db, rule_id, inserts, run_context)
    assert len(findings) == 1
    assert validate_finding(findings[0]) == []
    assert findings[0]["rule_id"] == rule_id


@pytest.mark.parametrize(("rule_id", "inserts"), CASES, ids=[c[0] for c in CASES])
def test_execution_is_deterministic(db, run_context, rule_id, inserts) -> None:
    """Regel 9: gleicher Input -> identische IDs in identischer Reihenfolge."""
    first = _run(db, rule_id, inserts, run_context)
    second = execute_rule(db, RULES[rule_id], run_context)
    assert [f["finding_id"] for f in first] == [f["finding_id"] for f in second]
    assert first == second


def test_payment_does_not_net_a_double_payment(db, run_context) -> None:
    """Eine bezahlte Doppelzahlung ohne Gutschrift bleibt ein Treffer (D-082).

    Der Stolperdraht zum Bug: beim Kreditor ist die Zahlung ebenso Soll wie die
    Gutschrift. Ohne die Einschraenkung auf `doc_type = 'KG'` nettete jede Zahlung ihr
    eigenes Rechnungspaar weg, und AP-LEA-001 fand auf echten Daten nie etwas - im
    Demo-Mandanten waren es 0 statt 8 Findings.
    """
    findings = _run(
        db, "AP-LEA-001", INSERT_AP_LEA_001 + INSERT_AP_LEA_001_PAYMENTS, run_context
    )
    assert len(findings) == 1
    assert validate_finding(findings[0]) == []


def test_credit_memo_nets_a_double_payment(db, run_context) -> None:
    """Die echte Gutschrift nettet weiterhin – die Gegenprobe zum Test darueber."""
    findings = _run(
        db,
        "AP-LEA-001",
        INSERT_AP_LEA_001 + INSERT_AP_LEA_001_PAYMENTS + INSERT_AP_LEA_001_CREDIT_MEMO,
        run_context,
    )
    assert findings == []


def test_defaults_come_from_the_rule_head(db, run_context) -> None:
    finding = _run(db, "AR-VAL-001", INSERT_AR_VAL_001, run_context)[0]
    rule = RULES["AR-VAL-001"]
    assert finding["tier"] == rule.default_tier
    assert finding["action_type"] == rule.default_action_type
    assert finding["severity"] == rule.severity
    assert finding["damage_class"] == rule.damage_class
    assert finding["rule_version"] == rule.version


def test_run_context_fills_head_fields(db, run_context) -> None:
    finding = _run(db, "AR-VAL-001", INSERT_AR_VAL_001, run_context)[0]
    assert finding["run_id"] == run_context.run_id
    assert finding["data_as_of"] == run_context.data_as_of
    assert finding["created_at"] == run_context.created_at
    assert finding["status"] == "open"


def test_params_fill_placeholders(db, run_context) -> None:
    finding = _run(db, "AR-VAL-001", INSERT_AR_VAL_001, run_context)[0]
    assert "{country}" not in finding["title"]
    assert finding["title"].endswith("(DE)")


def test_amount_is_decimal_text(db, run_context) -> None:
    """Regel 2: Betrag als Text mit zwei Dezimalen, nie float."""
    finding = _run(db, "AR-CON-002", INSERT_AR_CON_002, run_context)[0]
    assert finding["impact_eur"]["amount"] == "100.00"
    assert isinstance(finding["impact_eur"]["amount"], str)


def test_documents_and_options_are_decoded(db, run_context) -> None:
    pair = _run(db, "AP-LEA-001", INSERT_AP_LEA_001, run_context)[0]
    assert [d["document_no"] for d in pair["entity"]["documents"]] == ["10", "11"]
    decision = _run(db, "AR-CON-002", INSERT_AR_CON_002, run_context)[0]
    assert len(decision["proposed"]["options"]) == 2


# --- finding_id ----------------------------------------------------------------------


def test_finding_id_format() -> None:
    value = finding_id_for("AR-VAL-001", {"bp_key": "C:0000000001"})
    assert value.startswith("F-")
    assert len(value) == 14


def test_finding_id_ignores_columns_outside_the_formula() -> None:
    base = {"bp_key": "C:0000000001", "source_table": "KNA1", "source_field": "STCEG"}
    assert finding_id_for("AR-VAL-001", base) == finding_id_for(
        "AR-VAL-001", {**base, "source_summary": "andere Quellenlage"}
    )


@pytest.mark.parametrize(
    "column", ["bp_key", "company_code", "source_table", "source_field", "current_value", "finding_key"]
)
def test_finding_id_changes_with_each_formula_column(column) -> None:
    base = {"bp_key": "C:0000000001", "company_code": "1000", "source_table": "KNA1",
            "source_field": "STCEG", "current_value": "X", "finding_key": "K"}
    assert finding_id_for("AR-VAL-001", base) != finding_id_for(
        "AR-VAL-001", {**base, column: "anders"}
    )


def test_finding_id_changes_with_rule_id() -> None:
    row = {"bp_key": "C:0000000001"}
    assert finding_id_for("AR-VAL-001", row) != finding_id_for("AP-VAL-001", row)


def test_null_and_empty_string_hash_alike() -> None:
    """Dokumentiert das bewusste Verhalten: NULL wird als leerer Text behandelt."""
    assert finding_id_for("X", {"bp_key": None}) == finding_id_for("X", {"bp_key": ""})


def test_company_code_separates_findings_per_company(db, run_context) -> None:
    """Ohne company_code im Hash wuerden die beiden Buchungskreise kollidieren (D-027)."""
    db.execute(INSERT_AR_CON_002)
    # Der zweite Buchungskreis braucht seine T001-Zeile: das Waehrungsetikett kommt seit
    # D-205 von dort. Vorbedingung, keine geaenderte Erwartung – geprueft wird weiterhin,
    # dass zwei Buchungskreise zwei Findings ergeben.
    db.execute("""
        INSERT INTO company_code (company_code, name, currency, country)
        VALUES ('2000','Demo Vertrieb GmbH','EUR','DE');
        INSERT INTO bp_company_code (bp_key, company_code) VALUES ('C:0000000002','2000');
        INSERT INTO fi_item (item_key,bp_key,company_code,fiscal_year,document_no,line_item,
                             posting_date,currency,amount_doc,amount_local,amount_signed_local,is_open)
        VALUES ('2000|2026|2|1','C:0000000002','2000','2026','2','1',DATE '2026-01-05','EUR',
                100.00,100.00,100.00,TRUE);
    """)
    findings = execute_rule(db, RULES["AR-CON-002"], run_context)
    assert len(findings) == 2
    assert len({f["finding_id"] for f in findings}) == 2


def test_finding_key_separates_document_pairs(db, run_context) -> None:
    """Drei Belege mit identischer Referenz ergeben drei Paare mit gleichem Ist-Wert."""
    db.execute(INSERT_AP_LEA_001.replace("'RE-1','RE1'", "'RE1','RE1'").replace(
        "'RE 1','RE1'", "'RE1','RE1'"))
    db.execute("""
        INSERT INTO fi_item (item_key,bp_key,company_code,fiscal_year,document_no,line_item,
                             posting_date,document_date,doc_type,debit_credit,currency,
                             amount_doc,amount_local,amount_signed_local,reference,reference_norm,is_open)
        VALUES ('1000|2026|12|1','V:0000000003','1000','2026','12','1',DATE '2026-02-20',
                DATE '2026-02-20','KR','H','EUR',500.00,500.00,-500.00,'RE1','RE1',FALSE);
    """)
    findings = execute_rule(db, RULES["AP-LEA-001"], run_context)
    assert len(findings) == 3
    assert len({f["current"]["value"] for f in findings}) == 1
    assert len({f["finding_id"] for f in findings}) == 3


# --- Ausgabe-Vertrag -----------------------------------------------------------------

RULE_HEAD = """/* ---
id: AR-VAL-009
version: "1.0"
title: "Testregel"
side: AR
category: validity
severity: medium
damage_class: {damage_class}
default_tier: {default_tier}
default_action_type: {default_action_type}
requires_tables: [business_partner]
plain_logic: >
  Testregel fuer den Executor, fachlich ohne Bedeutung.
why: >
  {why}
if_wrong: >
  Kein Schaden, reiner Testfall.
remediation:
  sap_transaction: XD02
  mass_change_eligible: {mass_change_eligible}
tests:
  hits: ["C:0000000001"]
  no_hits: ["C:0000000002"]
  edge: []
--- */
{sql}
"""


def _rule(sql: str, **overrides):
    head = {
        "damage_class": 3,
        "default_tier": "C",
        "default_action_type": "review",
        "mass_change_eligible": "false",
        "why": "Testregel, fachlich ohne Bedeutung.",
        "sql": sql,
    }
    head.update(overrides)
    from pathlib import Path

    return parse_rule(RULE_HEAD.format(**head), Path("AR-VAL-009.rule.sql"))


BASE_SELECT = (
    "SELECT 'C:0000000001' AS bp_key, 'CUSTOMER' AS role, 'KNA1' AS source_table, "
    "'STCEG' AS source_field, 'X' AS current_value"
)


def test_missing_required_column_is_reported(db, run_context) -> None:
    rule = _rule("SELECT 'C:0000000001' AS bp_key, 'CUSTOMER' AS role;")
    with pytest.raises(ExecutionError) as excinfo:
        execute_rule(db, rule, run_context)
    assert "source_table" in str(excinfo.value)


def test_unknown_column_is_reported(db, run_context) -> None:
    """Regel 4: nichts wird stumm verworfen."""
    rule = _rule(f"{BASE_SELECT}, 'x' AS erfundene_spalte;")
    with pytest.raises(ExecutionError) as excinfo:
        execute_rule(db, rule, run_context)
    assert "erfundene_spalte" in str(excinfo.value)


def test_missing_table_is_reported(db, run_context) -> None:
    rule = _rule(f"{BASE_SELECT};")
    object.__setattr__(rule, "requires_tables", ("gibt_es_nicht",))
    assert missing_tables(db, rule) == ["gibt_es_nicht"]
    with pytest.raises(ExecutionError) as excinfo:
        execute_rule(db, rule, run_context)
    assert "gibt_es_nicht" in str(excinfo.value)


def test_sql_error_is_reported(db, run_context) -> None:
    rule = _rule("SELECT * FROM tabelle_ohne_namen;")
    with pytest.raises(ExecutionError) as excinfo:
        execute_rule(db, rule, run_context)
    assert "AR-VAL-009" in str(excinfo.value)


def test_missing_placeholder_is_reported(db, run_context) -> None:
    rule = _rule(f"{BASE_SELECT};", why="Betrag {amount} fehlt in params.")
    with pytest.raises(ExecutionError) as excinfo:
        execute_rule(db, rule, run_context)
    assert "amount" in str(excinfo.value)


def test_float_amount_is_rejected(db, run_context) -> None:
    """Regel 2: kein float fuer Betraege – auch nicht aus dem SQL."""
    rule = _rule(
        f"{BASE_SELECT}, CAST(640.0 AS DOUBLE) AS impact_amount, "
        "'EUR' AS impact_currency, 'Test' AS impact_formula;"
    )
    with pytest.raises(ExecutionError) as excinfo:
        execute_rule(db, rule, run_context)
    assert "float" in str(excinfo.value)


def test_amount_with_more_than_two_decimals_is_rejected(db, run_context) -> None:
    rule = _rule(
        f"{BASE_SELECT}, CAST(640.005 AS DECIMAL(15,3)) AS impact_amount, "
        "'EUR' AS impact_currency, 'Test' AS impact_formula;"
    )
    with pytest.raises(ExecutionError) as excinfo:
        execute_rule(db, rule, run_context)
    assert "Nachkommastellen" in str(excinfo.value)


def test_amount_keeps_sign(db, run_context) -> None:
    rule = _rule(
        f"{BASE_SELECT}, CAST(-640.00 AS DECIMAL(15,2)) AS impact_amount, "
        "'EUR' AS impact_currency, 'Test' AS impact_formula;"
    )
    assert execute_rule(db, rule, run_context)[0]["impact_eur"]["amount"] == "-640.00"


def test_row_overrides_head_defaults(db, run_context) -> None:
    rule = _rule(
        f"{BASE_SELECT}, 'decision' AS tier, 'decision' AS action_type;",
        default_tier="C",
    )
    finding = execute_rule(db, rule, run_context)[0]
    assert finding["tier"] == "decision"
    assert finding["action_type"] == "decision"


def test_dynamic_tier_a_for_damage_class_1_is_rejected(db, run_context) -> None:
    """Regel 11 gilt auch dynamisch, nicht nur im Regelkopf."""
    rule = _rule(
        f"{BASE_SELECT}, 'A' AS tier, 'Soll' AS proposed_value, 'Quelle' AS source_summary;",
        damage_class=1,
        default_tier="C",
    )
    with pytest.raises(ExecutionError) as excinfo:
        execute_rule(db, rule, run_context)
    assert "Schadensklasse 1 darf nie Stufe A sein" in str(excinfo.value)


def test_collision_without_finding_key_is_an_error(db, run_context) -> None:
    """Zwei identische Zeilen ohne unterscheidendes Merkmal = Fehler, nicht stille Dublette."""
    rule = _rule(f"{BASE_SELECT} UNION ALL {BASE_SELECT};")
    with pytest.raises(ExecutionError) as excinfo:
        execute_rule(db, rule, run_context)
    assert "finding_key" in str(excinfo.value)


def test_invalid_json_column_is_reported(db, run_context) -> None:
    rule = _rule(f"{BASE_SELECT}, 'kein json' AS evidence;")
    with pytest.raises(ExecutionError) as excinfo:
        execute_rule(db, rule, run_context)
    assert "evidence" in str(excinfo.value)


# --- Relevanz ------------------------------------------------------------------------


def test_relevance_is_filled_from_bp_relevance(db, run_context) -> None:
    db.execute(INSERT_AR_VAL_001)
    db.execute("""
        INSERT INTO bp_relevance (bp_key, open_items_local, volume_12m_local, currency,
                                  last_activity_on, activity_status)
        VALUES ('C:0000000001', 45210.00, 312400.00, 'EUR', DATE '2026-08-12', 'active');
    """)
    finding = execute_rule(db, RULES["AR-VAL-001"], run_context)[0]
    assert finding["relevance"] == {
        "open_items": "45210.00",
        "volume_12m": "312400.00",
        "currency": "EUR",
        "last_activity_on": "2026-08-12",
    }
    assert validate_finding(finding) == []


def test_relevance_is_absent_without_matching_row(db, run_context) -> None:
    finding = _run(db, "AR-VAL-001", INSERT_AR_VAL_001, run_context)[0]
    assert "relevance" not in finding


def test_relevance_amount_never_float(db, run_context) -> None:
    db.execute(INSERT_AR_VAL_001)
    db.execute("""
        INSERT INTO bp_relevance (bp_key, open_items_local, volume_12m_local, currency,
                                  last_activity_on, activity_status)
        VALUES ('C:0000000001', 0.00, 0.00, 'EUR', NULL, 'never_posted');
    """)
    relevance = execute_rule(db, RULES["AR-VAL-001"], run_context)[0]["relevance"]
    assert relevance["open_items"] == "0.00"
    assert relevance["last_activity_on"] is None


# --- Hauswaehrung (D-030) ------------------------------------------------------------


def test_house_currency_is_none_without_relevance_rows(db) -> None:
    assert house_currency(db) is None


def test_house_currency_returns_the_single_currency(db) -> None:
    db.execute("""
        INSERT INTO bp_relevance (bp_key, open_items_local, volume_12m_local, currency,
                                  last_activity_on, activity_status)
        VALUES ('C:0000000001', 1.00, 1.00, 'CHF', NULL, 'active');
    """)
    assert house_currency(db) == "CHF"


def test_multiple_house_currencies_abort_the_run(db, run_context) -> None:
    """V1 rechnet nicht um; zwei Hauswaehrungen im Scope brechen den Lauf ab (D-030)."""
    db.execute(INSERT_AR_VAL_001)
    db.execute("""
        INSERT INTO bp_relevance (bp_key, open_items_local, volume_12m_local, currency,
                                  last_activity_on, activity_status)
        VALUES ('C:0000000001', 1.00, 1.00, 'EUR', NULL, 'active'),
               ('C:0000000009', 2.00, 2.00, 'CHF', NULL, 'active');
    """)
    with pytest.raises(ExecutionError) as excinfo:
        house_currency(db)
    assert "Hauswaehrungen" in str(excinfo.value)
    with pytest.raises(ExecutionError):
        execute_rule(db, RULES["AR-VAL-001"], run_context)


def test_relevance_currency_is_not_assumed_eur(db, run_context) -> None:
    """Der Betrag wird nicht umgerechnet – die Waehrung steht daneben (Regel 2)."""
    db.execute(INSERT_AR_VAL_001)
    db.execute("""
        INSERT INTO bp_relevance (bp_key, open_items_local, volume_12m_local, currency,
                                  last_activity_on, activity_status)
        VALUES ('C:0000000001', 45210.00, 312400.00, 'CHF', DATE '2026-08-12', 'active');
    """)
    relevance = execute_rule(db, RULES["AR-VAL-001"], run_context)[0]["relevance"]
    assert relevance["currency"] == "CHF"
    assert relevance["open_items"] == "45210.00"


# --- AR-CON-002: Hauswaehrung statt Belegwaehrung (D-205) ----------------------------


def test_ar_con_002_zwei_belegwaehrungen_ergeben_ein_finding(db, run_context) -> None:
    """Ein Konto, ein Buchungskreis, zwei Belegwaehrungen – **ein** Finding.

    Bis D-205 stand die Belegwaehrung im GROUP BY: der Lauf brach hier mit
    „der Regel fehlt eine finding_key-Spalte" ab, weil beide Zeilen dieselbe Identitaet
    trugen (D-027).
    """
    findings = _run(db, "AR-CON-002", INSERT_AR_CON_002_ZWEI_WAEHRUNGEN, run_context)
    assert len(findings) == 1
    assert findings[0]["entity"]["company_code"] == "1000"


def test_ar_con_002_summiert_in_hauswaehrung(db, run_context) -> None:
    """Summiert wird `amount_signed_local` – der DMBTR-Betrag, nicht der Belegbetrag."""
    finding = _run(db, "AR-CON-002", INSERT_AR_CON_002_ZWEI_WAEHRUNGEN, run_context)[0]
    # 100.00 (EUR-Beleg) + 220.00 (DMBTR der USD-Rechnung) - nicht 100.00 + 250.00
    assert finding["impact_eur"]["amount"] == "320.00"


def test_ar_con_002_etikettiert_mit_der_hauswaehrung(db, run_context) -> None:
    """Neben dem Betrag steht die Waehrung des Buchungskreises, nie die des Belegs."""
    finding = _run(db, "AR-CON-002", INSERT_AR_CON_002_ZWEI_WAEHRUNGEN, run_context)[0]
    assert finding["impact_eur"]["currency"] == "EUR"
    assert "320,00 EUR" in finding["proposed"]["source_summary"]
    assert finding["evidence"][0]["value"] == "320,00 EUR"


def test_ar_con_002_nennt_die_belegwaehrung_nirgends(db, run_context) -> None:
    """Regel 2 andersherum: ein falsches Etikett ist schlimmer als keines.

    Geprueft ueber das **ganze** Finding und nicht feldweise – ein Feld, an das beim
    naechsten Umbau niemand denkt, faellt damit auf (Muster D-105).
    """
    finding = _run(db, "AR-CON-002", INSERT_AR_CON_002_ZWEI_WAEHRUNGEN, run_context)[0]
    assert "USD" not in json.dumps(finding, ensure_ascii=False)


def test_ar_con_002_folgt_der_hauswaehrung_des_mandanten(db, run_context) -> None:
    """CHF-Buchungskreis: dasselbe Finding, anderes Etikett – kein EUR im Code."""
    db.execute(
        INSERT_AR_CON_002_ZWEI_WAEHRUNGEN.replace(
            "VALUES ('1000','Demo Industrie AG','EUR','DE');",
            "VALUES ('1000','Demo Suisse AG','CHF','CH');",
        )
    )
    finding = execute_rule(db, RULES["AR-CON-002"], run_context)[0]
    assert finding["impact_eur"]["currency"] == "CHF"
    assert "320,00 CHF" in finding["proposed"]["source_summary"]


def test_ar_con_002_braucht_den_buchungskreis_stammsatz(db, run_context) -> None:
    """Ohne T001 gaebe es kein Waehrungsetikett – die Regel nennt die Tabelle deshalb."""
    assert "company_code" in RULES["AR-CON-002"].requires_tables


# --- Belegarten aus dem Woerterbuch (D-084) ------------------------------------------


def _doc_types(tmp_path, **sides):
    """Ein eigenes Woerterbuch fuer den Test – Belegarten sind Customizing, keine Daten."""
    spec = {
        "AR": {"invoice": ["DR"], "credit_memo": ["DG"], "payment": ["DZ"], "reversal": []},
        "AP": {"invoice": ["KR"], "credit_memo": ["KG"], "payment": ["KZ"], "reversal": []},
    }
    for side, classes in sides.items():
        spec[side].update(classes)
    return parse_document_types(
        {"version": "0.1", "sides": spec}, tmp_path / "document_types.yaml"
    )


def test_platzhalter_werden_durch_belegarten_ersetzt(run_context) -> None:
    """AP-LEA-001 traegt die Listen nicht mehr selbst – die Engine setzt sie ein."""
    sql = rule_sql(RULES["AP-LEA-001"], run_context)
    assert "${" not in sql
    assert "'KG'" in sql and "'KR'" in sql and "'RE'" in sql


def test_regel_ohne_platzhalter_bleibt_unveraendert(run_context) -> None:
    rule = RULES["AR-VAL-001"]
    assert rule_sql(rule, run_context) is rule.sql


def test_das_woerterbuch_entscheidet_wirklich(db, run_context, tmp_path) -> None:
    """Stolperdraht: kaeme die Liste weiter aus dem SQL, aenderte ein anderes
    Woerterbuch nichts. Ohne KR als Rechnung findet die Regel das Paar nicht mehr."""
    db.execute(INSERT_AP_LEA_001)
    assert len(execute_rule(db, RULES["AP-LEA-001"], run_context)) == 1

    ohne_kr = dataclasses.replace(
        run_context, doc_types=_doc_types(tmp_path, AP={"invoice": ["RE"]})
    )
    assert execute_rule(db, RULES["AP-LEA-001"], ohne_kr) == []


def test_leere_klasse_ist_ein_fehler_mit_namen(run_context, tmp_path) -> None:
    """Eine leere Werteliste waere eine stumm weggelassene Bedingung (Regel 4)."""
    rule = _rule(BASE_SELECT + " WHERE 'X' IN (${doc_types.AP.reversal})")
    ctx = dataclasses.replace(run_context, doc_types=_doc_types(tmp_path))
    with pytest.raises(ExecutionError) as excinfo:
        rule_sql(rule, ctx)
    assert "AP.reversal" in str(excinfo.value)


def test_unbekannter_platzhalter_wird_benannt(run_context, tmp_path) -> None:
    rule = _rule(BASE_SELECT + " WHERE 'X' = '${doc_types.AP.rechnungen}'")
    ctx = dataclasses.replace(run_context, doc_types=_doc_types(tmp_path))
    with pytest.raises(ExecutionError) as excinfo:
        rule_sql(rule, ctx)
    assert "rechnungen" in str(excinfo.value)


def test_klassen_lassen_sich_verbinden(run_context, tmp_path) -> None:
    """`credit_memo+reversal` – der Weg, auf dem D-082 spaeter geschlossen wird."""
    rule = _rule(BASE_SELECT + " WHERE 'X' IN (${doc_types.AP.credit_memo+reversal})")
    ctx = dataclasses.replace(
        run_context, doc_types=_doc_types(tmp_path, AP={"reversal": ["KA"]})
    )
    sql = rule_sql(rule, ctx)
    assert "'KA'" in sql and "'KG'" in sql


# --- RunContext ----------------------------------------------------------------------


def test_run_context_is_frozen(run_context) -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        run_context.run_id = "anders"  # type: ignore[misc]


def test_decimal_is_used_not_float() -> None:
    """Absicherung der Annahme: DuckDB liefert DECIMAL als Decimal."""
    import duckdb

    value = duckdb.connect().execute("SELECT CAST(1.5 AS DECIMAL(15,2))").fetchone()[0]
    assert isinstance(value, Decimal)


# --- Benannte Schwellen aus dem Regelkopf (D-107) ------------------------------------


def test_parameter_aus_dem_kopf_wird_eingesetzt(db, run_context) -> None:
    """`${params.<name>}` kommt aus `parameters` im Regelkopf, nicht aus dem SQL."""
    text = VALID_RULE_TEXT.replace(
        "tests:", "parameters:\n  min_invoices: 3\ntests:"
    ).replace("WHERE FALSE", "WHERE ${params.min_invoices} = 3")
    rule = parse_rule(text, Path("AR-VAL-009.rule.sql"))
    assert "${" not in rule_sql(rule, run_context)
    assert "3 = 3" in rule_sql(rule, run_context)


def test_parameter_ohne_eintrag_ist_ein_fehler_mit_namen(db, run_context) -> None:
    """Ein Platzhalter ohne Eintrag ist kein stiller Vorgabewert (Regel 4)."""
    text = VALID_RULE_TEXT.replace("WHERE FALSE", "WHERE ${params.min_invoices} = 3")
    rule = parse_rule(text, Path("AR-VAL-009.rule.sql"))
    with pytest.raises(ExecutionError) as excinfo:
        rule_sql(rule, run_context)
    assert "min_invoices" in str(excinfo.value)
    assert "parameters" in str(excinfo.value)


def test_vat_muster_werden_als_wertepaare_eingesetzt(run_context) -> None:
    """`${vat_patterns.rows}` wird zu SQL-Wertepaaren aus dem Woerterbuch (D-101)."""
    rule = RULES["AR-VAL-002"]
    sql = rule_sql(rule, run_context)
    assert "${" not in sql
    assert "('DE', '^DE\\d{9}$')" in sql


def test_fensterbeginn_wird_eingesetzt(run_context) -> None:
    """`${scope.item_window_from}` kommt aus dem Lauf, nicht aus der Regel (D-110)."""
    ctx = dataclasses.replace(run_context, item_window_from=date(2024, 9, 2))
    sql = rule_sql(RULES["AR-HYG-001"], ctx)
    assert "${" not in sql
    assert "DATE '2024-09-02'" in sql


def test_fensterbeginn_ohne_posten_ist_ein_fehler_mit_namen(run_context) -> None:
    """Ohne Posten gibt es kein Fenster – und 'angelegt vor Fensterbeginn' keine Antwort."""
    with pytest.raises(ExecutionError) as excinfo:
        rule_sql(RULES["AR-HYG-001"], run_context)
    assert "item_window_from" in str(excinfo.value)
    assert "keinen Posten" in str(excinfo.value)


def test_stichtag_wird_eingesetzt(run_context) -> None:
    """`${scope.data_as_of}` kommt aus dem Lauf, nicht aus `current_date`.

    Eine Regel, die "Frist verstrichen" oder "letzte zwoelf Monate" braucht, haette mit
    `current_date` morgen andere Findings auf demselben Input (Regel 9, D-028).
    """
    sql = rule_sql(RULES["AP-LEA-002"], run_context)
    assert "${" not in sql
    assert "DATE '2026-08-28'" in sql
    assert "current_date" not in sql.lower()


def test_betragsschwelle_bleibt_exakt(run_context) -> None:
    """Eine Schwelle, die ein Betrag ist, geht als Zeichenkette ins SQL (Regel 2).

    Als YAML-Zahl waere aus `1000.00` ein float geworden und der Vergleich haette den
    DECIMAL-Betrag auf die Fliesskommaseite gezogen.
    """
    rule = RULES["AP-LEA-002"]
    assert rule.parameters["min_loss"] == "1000.00"
    sql = rule_sql(rule, run_context)
    assert "'1000.00'::DECIMAL(15,2)" in sql


def test_platzhalterbegriffe_werden_als_regex_eingesetzt(run_context) -> None:
    """`${placeholder_terms.pattern}` wird zu einem fertigen Regex (D-102)."""
    sql = rule_sql(RULES["AR-VAL-005"], dataclasses.replace(run_context))
    assert "${placeholder_terms" not in sql
    assert "xxx" in sql


# --- entity.display_name (D-185) -----------------------------------------------------


def test_anzeigename_faellt_weg_wenn_beide_felder_fehlen(db) -> None:
    """Ein Komma ohne Namen ist kein Name – dann bleibt das Feld weg."""
    db.execute(
        "INSERT INTO business_partner (bp_key, role, source_id, name1, city) "
        "VALUES ('C:0000000009', 'CUSTOMER', '9', NULL, NULL)"
    )
    assert _display_names_by_bp(db, ["C:0000000009"]) == {}


def test_anzeigename_nimmt_das_vorhandene_feld(db) -> None:
    db.execute(
        "INSERT INTO business_partner (bp_key, role, source_id, name1, city) VALUES "
        "('C:0000000010', 'CUSTOMER', '10', 'Beispiel GmbH', NULL), "
        "('C:0000000011', 'CUSTOMER', '11', 'Beispiel AG', 'Beispielstadt')"
    )
    namen = _display_names_by_bp(db, ["C:0000000010", "C:0000000011"])
    assert namen["C:0000000010"] == "Beispiel GmbH"
    assert namen["C:0000000011"] == "Beispiel AG, Beispielstadt"


def test_anzeigename_aendert_die_finding_id_nicht() -> None:
    """Der Name gehoert nicht in den Schluessel – sonst verschoebe eine Umbenennung ihn."""
    assert "display_name" not in ID_COLUMNS


def test_proposed_ohne_soll_bricht_den_lauf_ab(db, run_context) -> None:
    """Nur eine Quellenlage und kein Soll: das ist ein leerer Vorschlag (D-186)."""
    text = VALID_RULE_TEXT.replace(
        "SELECT bp_key, role FROM business_partner WHERE FALSE ORDER BY bp_key;",
        "SELECT bp_key, role, 'KNA1' AS source_table, 'STCEG' AS source_field, "
        "'X' AS current_value, 'ohne Soll, nur Erklaerung' AS source_summary "
        "FROM business_partner ORDER BY bp_key;",
    )
    rule = parse_rule(text, Path("AR-VAL-009.rule.sql"))
    db.execute(
        "INSERT INTO business_partner (bp_key, role, source_id) "
        "VALUES ('C:0000000001', 'CUSTOMER', '1')"
    )
    with pytest.raises(InvalidFindingError) as excinfo:
        execute_rule(db, rule, run_context)
    assert "kein Soll" in str(excinfo.value)
    assert "remediation" in str(excinfo.value)
