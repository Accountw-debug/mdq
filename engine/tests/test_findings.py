"""Schema-Validierung von Findings."""

import json
import re

import pytest
from typer.testing import CliRunner

from mdq import LOGIC_DIR, RULES_DIR
from mdq.cli import EXIT_INVALID, EXIT_NO_INPUT, app
from mdq.findings import (
    FindingFileError,
    duplicate_finding_ids,
    iter_finding_files,
    load_finding_file,
    load_schema,
    schema_version,
    validate_finding,
)
from mdq.rules import load_rules

runner = CliRunner()

EXAMPLE_FILES = sorted((LOGIC_DIR / "examples" / "findings").glob("*.yaml"))


def test_examples_exist() -> None:
    """Ohne Beispiele wuerde die parametrisierte Pruefung stumm nichts pruefen."""
    assert EXAMPLE_FILES


@pytest.mark.parametrize("path", EXAMPLE_FILES, ids=lambda p: p.name)
def test_example_findings_are_valid(path) -> None:
    assert validate_finding(load_finding_file(path)) == []


@pytest.mark.parametrize("path", EXAMPLE_FILES, ids=lambda p: p.name)
def test_example_finding_matches_its_rule_version(path) -> None:
    """Ein Beispiel-Finding nennt die Version der Regel, die es zeigt.

    F-006 trug `1.0` und zeigte eine Euro-Wirkung, die erst 1.1 liefert (D-196) – ein
    halbes Jahr spaeter haette niemand mehr gewusst, welche der beiden Angaben stimmt.
    Diese Klammer faellt auf, sobald eine Regelversion steigt und ihr Beispiel nicht.

    Schlaegt sie an, ist die Antwort **nicht**, das Beispiel nachzuziehen: die Dateien in
    `logic/examples/` sind Victors fachliche Spec (Regel 1). Entweder das Beispiel zeigt
    etwas, das die neue Version so nicht mehr liefert – dann gehoert es besprochen –,
    oder die Versionsangabe hinkt nach und wird ausdruecklich freigegeben.
    """
    finding = load_finding_file(path)
    versions = {rule.id: rule.version for rule in load_rules(RULES_DIR)}
    rule_id = finding["rule_id"]
    if rule_id not in versions:
        pytest.skip(f"{rule_id} ist noch nicht gebaut")
    assert finding["rule_version"] == versions[rule_id], (
        f"{path.name}: Beispiel nennt {finding['rule_version']}, "
        f"{rule_id} steht auf {versions[rule_id]}"
    )


def test_minimal_finding_is_valid(minimal_finding) -> None:
    assert validate_finding(minimal_finding) == []


def test_title_is_required(minimal_finding) -> None:
    """Jedes Finding traegt einen Titel; die Engine fuellt ihn aus dem Regelkopf."""
    del minimal_finding["title"]
    assert any("title" in message for message in validate_finding(minimal_finding))


def test_empty_title_is_rejected(minimal_finding) -> None:
    """Pflichtfeld mit leerem Text waere ein Titel, der keiner ist."""
    minimal_finding["title"] = ""
    assert validate_finding(minimal_finding)


# --- Invarianten aus dem Schema ------------------------------------------------------


def test_damage_class_1_must_not_be_tier_a(minimal_finding) -> None:
    """CLAUDE.md Regel 11 / D-005: Bankdaten werden nie Stufe A."""
    minimal_finding["damage_class"] = 1
    minimal_finding["tier"] = "A"
    minimal_finding["proposed"] = {"value": "DE00", "source_summary": "Testquelle"}
    errors = validate_finding(minimal_finding)
    assert errors
    assert any("Schadensklasse 1 darf nie Stufe A sein" in message for message in errors)


def test_tier_a_requires_proposed(minimal_finding) -> None:
    minimal_finding["tier"] = "A"
    errors = validate_finding(minimal_finding)
    assert any("Stufe A und B brauchen ein Soll" in message for message in errors)


def test_mass_change_requires_tier_a(minimal_finding) -> None:
    minimal_finding["action_type"] = "mass_change"
    minimal_finding["tier"] = "B"
    minimal_finding["proposed"] = {"value": "DE00", "source_summary": "Testquelle"}
    errors = validate_finding(minimal_finding)
    assert any("mass_change nur bei Stufe A" in message for message in errors)


# --- Datentypen und Formate ----------------------------------------------------------


def test_float_amount_is_rejected(minimal_finding) -> None:
    """CLAUDE.md Regel 2: Betraege nie als float."""
    minimal_finding["impact_eur"] = {
        "amount": 640.00,
        "currency": "EUR",
        "formula": "32000.00 x 2 % = 640.00",
    }
    assert any("impact_eur.amount" in message for message in validate_finding(minimal_finding))


def test_amount_needs_two_decimals(minimal_finding) -> None:
    minimal_finding["impact_eur"] = {"amount": "640", "currency": "EUR", "formula": "Test"}
    assert any("impact_eur.amount" in message for message in validate_finding(minimal_finding))


def test_broken_date_time_is_rejected(minimal_finding) -> None:
    """Ohne eigenen Checker bliebe date-time still ungeprueft (D-018)."""
    minimal_finding["created_at"] = "gestern"
    assert any("created_at" in message for message in validate_finding(minimal_finding))


def test_valid_date_time_variants_are_accepted(minimal_finding) -> None:
    for value in ("2026-08-30T09:15:00Z", "2026-08-30T09:15:00+02:00", "2026-08-30T09:15:00"):
        minimal_finding["created_at"] = value
        assert validate_finding(minimal_finding) == [], value


def test_unknown_field_is_rejected(minimal_finding) -> None:
    """Regel 4: nichts wird stumm geschluckt."""
    minimal_finding["unbekanntes_feld"] = "x"
    assert any("unbekanntes_feld" in message for message in validate_finding(minimal_finding))



# --- Schema-Erweiterungen aus dem UI (Sprint 3, Aufgabe 0) ---------------------------

#: Ein vollstaendig gefuellter Beleg. Alle Werte erfunden (Regel 8).
DOCUMENT = {
    "company_code": "1000",
    "fiscal_year": "2026",
    "document_no": "1900004411",
    "line_item": "001",
    "reference": "RE-0001",
    "document_date": "2026-03-01",
    "cleared_on": "2026-03-28",
    "amount": "32000.00",
    "currency": "EUR",
}

#: Ein Kontosatz fuer den Feld-fuer-Feld-Vergleich. Alle Werte erfunden (Regel 8).
RECORD_FIELDS = {
    "name": "Testkonto Eins",
    "street": "Teststrasse 1",
    "postal_code": "86159",
    "city": "Testort",
    "country": "DE",
    "vat_id": "DE000000001",
    "iban_masked": "DE44 \u202649 32",
    "payment_terms": "ZB01",
    "open_items": "45210.00",
    "currency": "EUR",
    "last_activity_on": "2026-08-12",
}

GOLDEN_ENTRY = {
    "value": "DE000000001",
    "source_bp_key": "C:0000000002",
    "source_type": "duplicate_record",
}


def _with_document(finding: dict, **overrides) -> dict:
    finding["entity"]["documents"] = [DOCUMENT | overrides]
    return finding


def _with_record(finding: dict, **overrides) -> dict:
    finding["entity"]["records"] = [{"bp_key": "C:0000000001", "fields": RECORD_FIELDS | overrides}]
    return finding


def _with_golden_record(finding: dict, golden: dict) -> dict:
    finding["proposed"] = {
        "value": "0000000001",
        "source_summary": "Testfall Schema-Validierung",
        "golden_record": golden,
    }
    return finding


def test_schema_carries_a_version() -> None:
    """Die Version steht im Schema, nicht in jedem Finding (D-069)."""
    assert re.fullmatch(r"[0-9]+\.[0-9]+", schema_version())


def test_record_fields_and_golden_record_share_one_field_list() -> None:
    """Beide beschreiben dieselben Felder; zwei Listen duerfen nicht auseinanderlaufen."""
    schema = load_schema()
    records = schema["properties"]["entity"]["properties"]["records"]
    golden = schema["properties"]["proposed"]["properties"]["golden_record"]
    assert sorted(records["items"]["properties"]["fields"]["properties"]) == sorted(
        golden["properties"]
    )


def test_extended_document_fields_are_valid(minimal_finding) -> None:
    assert validate_finding(_with_document(minimal_finding)) == []


def test_document_amount_as_float_is_rejected(minimal_finding) -> None:
    """Regel 2: auch am Beleg ist der Betrag ein String mit zwei Dezimalen."""
    finding = _with_document(minimal_finding, amount=32000.00)
    assert any("entity.documents[0].amount" in m for m in validate_finding(finding))


def test_document_amount_needs_two_decimals(minimal_finding) -> None:
    finding = _with_document(minimal_finding, amount="32000")
    assert any("entity.documents[0].amount" in m for m in validate_finding(finding))


def test_document_cleared_on_must_be_a_date(minimal_finding) -> None:
    finding = _with_document(minimal_finding, cleared_on="gestern")
    assert any("entity.documents[0].cleared_on" in m for m in validate_finding(finding))


def test_unknown_document_field_is_rejected(minimal_finding) -> None:
    finding = _with_document(minimal_finding, waehrung="EUR")
    assert any("waehrung" in m for m in validate_finding(finding))


def test_reference_kind_is_accepted(minimal_finding) -> None:
    minimal_finding["evidence"] = [
        {
            "source_type": "deterministic",
            "reference": "BSAK Gutschriften",
            "reference_kind": "netting",
            "value": None,
            "agrees": True,
        }
    ]
    assert validate_finding(minimal_finding) == []


def test_unknown_reference_kind_is_rejected(minimal_finding) -> None:
    """Ein falscher Enum-Wert waere sonst ein Wort, das die UI nicht kennt."""
    minimal_finding["evidence"] = [
        {
            "source_type": "deterministic",
            "reference": "BSAK Gutschriften",
            "reference_kind": "beleg",
            "value": None,
            "agrees": True,
        }
    ]
    assert any("evidence[0].reference_kind" in m for m in validate_finding(minimal_finding))


def test_records_are_valid(minimal_finding) -> None:
    assert validate_finding(_with_record(minimal_finding)) == []


def test_record_with_unknown_field_is_rejected(minimal_finding) -> None:
    """Regel 4: ein zusaetzliches Feld ist ein Fehler, kein stiller Zusatz."""
    finding = _with_record(minimal_finding, kreditlimit="10000.00")
    assert any("kreditlimit" in m for m in validate_finding(finding))


def test_record_with_unknown_key_beside_fields_is_rejected(minimal_finding) -> None:
    _with_record(minimal_finding)
    minimal_finding["entity"]["records"][0]["role"] = "CUSTOMER"
    assert any("role" in m for m in validate_finding(minimal_finding))


def test_record_needs_bp_key_and_fields(minimal_finding) -> None:
    minimal_finding["entity"]["records"] = [{"fields": {}}]
    assert any("bp_key" in m for m in validate_finding(minimal_finding))


def test_record_open_items_as_float_is_rejected(minimal_finding) -> None:
    finding = _with_record(minimal_finding, open_items=45210.00)
    assert any("entity.records[0].fields.open_items" in m for m in validate_finding(finding))


def test_unmasked_iban_is_rejected(minimal_finding) -> None:
    """Regel 8: eine vollstaendige IBAN darf nicht in ein Finding geraten."""
    finding = _with_record(minimal_finding, iban_masked="DE44500105175407324932")
    assert any("entity.records[0].fields.iban_masked" in m for m in validate_finding(finding))


def test_masked_iban_variants_are_accepted(minimal_finding) -> None:
    for value in ("DE44 \u202649 32", "DE44\u20264932", "DE44...4932", "DE44 ***4932", None):
        assert validate_finding(_with_record(minimal_finding, iban_masked=value)) == [], value


def test_too_much_of_the_iban_visible_is_rejected(minimal_finding) -> None:
    """Hoechstens die ersten vier und die letzten vier Zeichen."""
    finding = _with_record(minimal_finding, iban_masked="DE4450 \u20264932 99")
    assert any("entity.records[0].fields.iban_masked" in m for m in validate_finding(finding))


def test_golden_record_is_valid(minimal_finding) -> None:
    assert validate_finding(_with_golden_record(minimal_finding, {"vat_id": GOLDEN_ENTRY})) == []


def test_golden_record_unknown_field_name_is_rejected(minimal_finding) -> None:
    """Die Feldnamen sind dieselben wie im Kontosatz; ein Tippfehler faellt auf."""
    finding = _with_golden_record(minimal_finding, {"ust_id": GOLDEN_ENTRY})
    assert any("ust_id" in m for m in validate_finding(finding))


def test_golden_record_entry_needs_its_source(minimal_finding) -> None:
    """Ohne Quellkonto waere es ein Wert ohne Herkunft."""
    entry = {k: v for k, v in GOLDEN_ENTRY.items() if k != "source_bp_key"}
    finding = _with_golden_record(minimal_finding, {"vat_id": entry})
    assert any("source_bp_key" in m for m in validate_finding(finding))


def test_golden_record_source_type_uses_the_evidence_list(minimal_finding) -> None:
    finding = _with_golden_record(minimal_finding, {"vat_id": GOLDEN_ENTRY | {"source_type": "geraten"}})
    assert any("golden_record.vat_id.source_type" in m for m in validate_finding(finding))


def test_decision_assigned_to_is_accepted(minimal_finding) -> None:
    """Der Empfaenger der Zuweisung – `by` ist der Entscheider, nicht der Bearbeiter."""
    minimal_finding["status"] = "rejected"
    minimal_finding["decision"] = {
        "by": "test.user",
        "at": "2026-08-30T09:15:00Z",
        "reason": "Testfall",
        "reason_code": "data_correct",
        "assigned_to": "test.kollege",
    }
    assert validate_finding(minimal_finding) == []


# --- Regel 8: keine Geschaeftspartnerdaten in Meldungen ------------------------------


def test_messages_never_quote_values(minimal_finding) -> None:
    secrets = ("Mustermann Handels GmbH", "DE02120300000000202051", "Hauptstrasse 1")
    minimal_finding["entity"]["display_name"] = secrets[0]
    minimal_finding["current"]["value"] = secrets[1]
    minimal_finding["current"]["display"] = secrets[2]
    minimal_finding["side"] = "XX"  # erzwingt einen Fehler
    errors = validate_finding(minimal_finding)
    assert errors
    joined = " ".join(errors)
    for secret in secrets:
        assert secret not in joined


def test_messages_never_quote_record_values(minimal_finding) -> None:
    """Auch die neuen Felder duerfen ihren Wert nicht in die Meldung tragen."""
    iban = "DE02120300000000202051"
    _with_record(minimal_finding, iban_masked=iban, name="Mustermann Handels GmbH")
    minimal_finding["entity"]["records"][0]["fields"]["country"] = "Deutschland"
    errors = validate_finding(minimal_finding)
    assert errors
    joined = " ".join(errors)
    assert iban not in joined
    assert "Mustermann Handels GmbH" not in joined
    assert "Deutschland" not in joined


# --- Determinismus (Regel 9) ---------------------------------------------------------


def test_error_order_is_deterministic(minimal_finding) -> None:
    minimal_finding["side"] = "XX"
    minimal_finding["severity"] = "sehr hoch"
    minimal_finding["damage_class"] = 9
    assert validate_finding(minimal_finding) == validate_finding(minimal_finding)
    assert len(validate_finding(minimal_finding)) == 3


# --- Laden von Dateien ---------------------------------------------------------------


def test_yaml_dates_stay_strings(tmp_path, minimal_finding) -> None:
    """Unquotiertes Datum wird nicht zum date-Objekt (D-019), sonst schluege die Pruefung
    mit einer irrefuehrenden Typmeldung fehl."""
    path = tmp_path / "f.yaml"
    path.write_text("data_as_of: 2026-08-28\ncreated_at: 2026-08-30T09:15:00Z\n", encoding="utf-8")
    document = load_finding_file(path)
    assert document["data_as_of"] == "2026-08-28"
    assert document["created_at"] == "2026-08-30T09:15:00Z"


def test_json_findings_are_loaded(tmp_path, minimal_finding) -> None:
    """D-007: Der Vertrag zur UI ist JSON."""
    path = tmp_path / "f.json"
    path.write_text(json.dumps(minimal_finding), encoding="utf-8")
    assert validate_finding(load_finding_file(path)) == []


def test_unparsable_file_raises(tmp_path) -> None:
    path = tmp_path / "kaputt.yaml"
    path.write_text("finding_id: [unbalanced\n", encoding="utf-8")
    with pytest.raises(FindingFileError):
        load_finding_file(path)


def test_non_mapping_file_raises(tmp_path) -> None:
    path = tmp_path / "liste.yaml"
    path.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(FindingFileError):
        load_finding_file(path)


def test_iter_finding_files_is_sorted_and_filters(tmp_path) -> None:
    (tmp_path / "b.yaml").write_text("{}", encoding="utf-8")
    (tmp_path / "a.json").write_text("{}", encoding="utf-8")
    (tmp_path / "README.md").write_text("kein Finding", encoding="utf-8")
    assert [p.name for p in iter_finding_files(tmp_path)] == ["a.json", "b.yaml"]


def test_iter_finding_files_missing_path_raises(tmp_path) -> None:
    with pytest.raises(FindingFileError):
        iter_finding_files(tmp_path / "gibtsnicht")


def test_duplicate_finding_ids_detected(tmp_path, minimal_finding) -> None:
    first, second = tmp_path / "a.yaml", tmp_path / "b.yaml"
    result = duplicate_finding_ids({first: minimal_finding, second: dict(minimal_finding)})
    assert result == {minimal_finding["finding_id"]: [first, second]}


# --- CLI -----------------------------------------------------------------------------


def test_cli_validate_examples(example_findings_dir) -> None:
    result = runner.invoke(app, ["validate", str(example_findings_dir)])
    assert result.exit_code == 0
    assert "0 fehlerhaft" in result.stdout


def test_cli_validate_reports_invalid(tmp_path, minimal_finding) -> None:
    minimal_finding["damage_class"] = 1
    minimal_finding["tier"] = "A"
    minimal_finding["proposed"] = {"value": "DE00", "source_summary": "Testquelle"}
    (tmp_path / "f.json").write_text(json.dumps(minimal_finding), encoding="utf-8")
    result = runner.invoke(app, ["validate", str(tmp_path)])
    assert result.exit_code == EXIT_INVALID
    assert "1 fehlerhaft" in result.stdout


def test_cli_validate_reports_duplicates(tmp_path, minimal_finding) -> None:
    for name in ("a.json", "b.json"):
        (tmp_path / name).write_text(json.dumps(minimal_finding), encoding="utf-8")
    result = runner.invoke(app, ["validate", str(tmp_path)])
    assert result.exit_code == EXIT_INVALID
    assert "doppelte finding_id" in result.stdout


def test_cli_validate_empty_directory(tmp_path) -> None:
    result = runner.invoke(app, ["validate", str(tmp_path)])
    assert result.exit_code == EXIT_NO_INPUT


def test_cli_validate_missing_path(tmp_path) -> None:
    result = runner.invoke(app, ["validate", str(tmp_path / "gibtsnicht")])
    assert result.exit_code == EXIT_NO_INPUT
