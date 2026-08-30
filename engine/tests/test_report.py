"""Run-Report: Inhalt, Determinismus und was nicht in der Ausgabe stehen darf."""

import io
import json
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

from mdq import PROJECT_ROOT
from mdq.cli import EXIT_INVALID, EXIT_NO_INPUT, app
from mdq.loader import LoadResult, load_table, record_reject
from mdq.report import (
    RejectSummary,
    RuleOutcome,
    RunReport,
    collect_rejects,
    render,
)

runner = CliRunner()
SAMPLES = PROJECT_ROOT / "testdata" / "encoding_samples"


def _text(report: RunReport, width: int = 100) -> str:
    buffer = io.StringIO()
    render(report, Console(file=buffer, width=width, no_color=True, soft_wrap=False))
    return buffer.getvalue()


def _load_result(table: str = "KNA1", warnings: tuple[str, ...] = ()) -> LoadResult:
    return LoadResult(
        table=table,
        path=Path(f"{table}_export.txt"),
        rows=5,
        encoding="UTF-8",
        delimiter="Tab",
        sha256="a" * 64,
        columns=("KUNNR", "LAND1"),
        warnings=warnings,
    )


@pytest.fixture
def report() -> RunReport:
    value = RunReport(
        run_id="test-run",
        engine_version="0.1.0",
        pack_version="0.1",
        data_as_of="2026-08-28",
        house_currency="EUR",
    )
    value.add_load(_load_result("KNA1"))
    value.add_load(_load_result("LFA1"))
    value.add_rule(RuleOutcome.executed("AR-VAL-001", findings=3))
    value.add_rule(RuleOutcome.executed("AP-LEA-001", findings=1))
    value.add_rule(RuleOutcome.skipped("AR-CON-002", ["fi_item"]))
    return value


# --- Inhalt --------------------------------------------------------------------------


def test_report_shows_all_sections(report) -> None:
    text = _text(report)
    for heading in ("Geladene Dateien", "Rejects", "Regeln"):
        assert heading in text
    assert "test-run" in text
    assert "EUR" in text


def test_report_lists_tables_and_rules(report) -> None:
    text = _text(report)
    for expected in ("KNA1", "LFA1", "AR-VAL-001", "AP-LEA-001", "AR-CON-002"):
        assert expected in text


def test_rules_are_sorted_by_id(report) -> None:
    assert [o.rule_id for o in report.sorted_rules] == ["AP-LEA-001", "AR-CON-002", "AR-VAL-001"]
    text = _text(report)
    assert text.index("AP-LEA-001") < text.index("AR-CON-002") < text.index("AR-VAL-001")


def test_findings_total_is_shown(report) -> None:
    assert report.findings_total == 4
    assert "4 Findings" in _text(report)


def test_skipped_rules_are_reported_with_reason(report) -> None:
    """CONCEPT.md Block 3: "nicht geprüft" wird ausgewiesen, nicht weggelassen."""
    text = _text(report)
    assert "übersprungen" in text
    assert "fi_item" in text
    assert "1 Regeln nicht geprüft" in text


def test_failed_rule_is_reported(report) -> None:
    report.add_rule(RuleOutcome.failed("AR-VAL-009", "SQL-Fehler"))
    text = _text(report)
    assert "fehlgeschlagen" in text
    assert "1 Regeln fehlgeschlagen" in text
    assert report.failed_rules


def test_cp1252_warning_is_visible(report) -> None:
    """Der geratene Fallback aus Aufgabe 5 muss im Report sichtbar sein (D-031)."""
    report.add_load(_load_result("KNB1", warnings=("KNB1.txt: als CP1252 gelesen.",))) 
    text = _text(report)
    assert "HINWEIS" in text
    assert "CP1252" in text


def test_empty_report_states_it_explicitly() -> None:
    text = _text(RunReport(run_id="leer"))
    assert "keine Dateien geladen" in text
    assert "keine Rejects" in text
    assert "keine Regeln ausgeführt" in text


# --- has_problems --------------------------------------------------------------------


def test_clean_report_has_no_problems() -> None:
    clean = RunReport(run_id="sauber")
    clean.add_load(_load_result())
    clean.add_rule(RuleOutcome.executed("AR-VAL-001", findings=0))
    assert clean.has_problems is False
    assert "Auffälligkeiten" not in _text(clean)


def test_skipped_rule_makes_problems(report) -> None:
    assert report.has_problems is True
    assert "Auffälligkeiten" in _text(report)


def test_rejects_make_problems() -> None:
    value = RunReport(run_id="mit-rejects")
    value.rejects = [RejectSummary(stage="staged", count=2, reasons=(("Betrag", 2),))]
    assert value.has_problems is True


# --- Regel 8: kein Rohtext in der Ausgabe --------------------------------------------


def test_raw_excerpt_never_reaches_the_output(canonical_db) -> None:
    """raw_excerpt bleibt in der Tabelle; der Report wird in Tickets kopiert (D-036)."""
    secret = "Mustermann Handels GmbH;DE02120300000000202051"
    record_reject(canonical_db, "run-1", "staged", "BSID", 7, "Betrag nicht parsebar", secret)
    value = RunReport(run_id="run-1")
    value.rejects = collect_rejects(canonical_db, "run-1")
    text = _text(value)
    assert "Betrag nicht parsebar" in text
    assert secret not in text
    assert "Mustermann" not in text


def test_collect_rejects_groups_by_stage(canonical_db) -> None:
    for _ in range(3):
        record_reject(canonical_db, "r", "raw", "KNA1", 1, "Spaltenzahl falsch", None)
    record_reject(canonical_db, "r", "staged", "BSID", 2, "Datum unbekannt", None)
    record_reject(canonical_db, "andere", "raw", "KNA1", 1, "gehört nicht dazu", None)

    summaries = collect_rejects(canonical_db, "r")
    assert [s.stage for s in summaries] == ["raw", "staged"]
    assert summaries[0].count == 3
    assert summaries[0].reasons == (("Spaltenzahl falsch", 3),)
    assert sum(s.count for s in summaries) == 4


def test_collect_rejects_is_empty_without_rows(canonical_db) -> None:
    assert collect_rejects(canonical_db, "gibt-es-nicht") == []


# --- to_dict -------------------------------------------------------------------------


def test_to_dict_is_json_serialisable(report) -> None:
    payload = json.dumps(report.to_dict(), ensure_ascii=False)
    assert "AR-VAL-001" in payload


def test_to_dict_matches_the_rendered_numbers(report) -> None:
    data = report.to_dict()
    assert data["totals"]["findings"] == report.findings_total
    assert data["totals"]["rules_executed"] == 2
    assert data["totals"]["rules_skipped"] == 1
    assert data["totals"]["rows"] == 10
    assert data["has_problems"] is True


def test_to_dict_keeps_the_full_sha(report) -> None:
    """Die Anzeige kürzt, das Datenobjekt nicht."""
    assert len(report.to_dict()["files"][0]["sha256"]) == 64


# --- Determinismus und Breite --------------------------------------------------------


def test_rendering_is_deterministic(report) -> None:
    assert _text(report) == _text(report)


def test_technical_values_are_not_truncated_at_80_columns(report) -> None:
    text = _text(report, width=80)
    for expected in ("AR-VAL-001", "AP-LEA-001", "AR-CON-002", "KNA1", "LFA1"):
        assert expected in text
    assert "UTF-8" in text


# --- CLI: mdq load -------------------------------------------------------------------


def test_cli_load_reports_the_samples() -> None:
    result = runner.invoke(app, ["load", "--input", str(SAMPLES)])
    assert result.exit_code == 0
    assert "5 Dateien" in result.stdout
    assert "KNA1" in result.stdout and "BSID" in result.stdout
    assert "CP1252" in result.stdout


def test_cli_load_marks_itself_as_interim() -> None:
    result = runner.invoke(app, ["load", "--input", str(SAMPLES)])
    assert "Zwischenstand" in result.stdout


def test_cli_load_missing_directory(tmp_path) -> None:
    result = runner.invoke(app, ["load", "--input", str(tmp_path / "gibtsnicht")])
    assert result.exit_code == EXIT_NO_INPUT


def test_cli_load_empty_directory(tmp_path) -> None:
    result = runner.invoke(app, ["load", "--input", str(tmp_path)])
    assert result.exit_code == EXIT_NO_INPUT


def test_cli_load_reports_broken_file(tmp_path) -> None:
    (tmp_path / "KNA1_kaputt.txt").write_text("KUNNR\n0000100234\n", encoding="utf-8")
    result = runner.invoke(app, ["load", "--input", str(tmp_path)])
    assert result.exit_code == EXIT_INVALID
    assert "Spaltentrenner" in result.output


def test_cli_load_uses_the_real_loader(canonical_db) -> None:
    """Gegenprobe: dieselben Dateien über load_table ergeben dieselben Zeilenzahlen."""
    rows = {load_table(canonical_db, path).rows for path in sorted(SAMPLES.glob("KNA1_*.txt"))}
    assert rows == {5}
