"""Schema-Validierung von Findings."""

import json

import pytest
from typer.testing import CliRunner

from mdq import LOGIC_DIR
from mdq.cli import EXIT_INVALID, EXIT_NO_INPUT, app
from mdq.findings import (
    FindingFileError,
    duplicate_finding_ids,
    iter_finding_files,
    load_finding_file,
    validate_finding,
)

runner = CliRunner()

EXAMPLE_FILES = sorted((LOGIC_DIR / "examples" / "findings").glob("*.yaml"))


def test_examples_exist() -> None:
    """Ohne Beispiele wuerde die parametrisierte Pruefung stumm nichts pruefen."""
    assert EXAMPLE_FILES


@pytest.mark.parametrize("path", EXAMPLE_FILES, ids=lambda p: p.name)
def test_example_findings_are_valid(path) -> None:
    assert validate_finding(load_finding_file(path)) == []


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
