"""Bootstrap: Paket importierbar, Schema-Fixture laedt, CLI-Geruest antwortet."""

from typer.testing import CliRunner

from mdq import __version__
from mdq.cli import app
from mdq.run import EXIT_ABORTED

runner = CliRunner()


def test_canonical_schema_is_loaded(canonical_db) -> None:
    rows = canonical_db.execute("SELECT table_name FROM duckdb_tables()").fetchall()
    tables = {row[0] for row in rows}
    assert {"business_partner", "reject", "fi_item", "run_meta"} <= tables


def test_version_command_succeeds() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_no_command_reports_an_empty_success(tmp_path) -> None:
    """Kein Befehl meldet einen leeren Erfolg (D-013).

    Seit Sprint 3, Aufgabe 4 gibt es keinen Stub mehr: `run` ist umgesetzt. Geprueft wird
    deshalb der Fall, in dem es nichts zu tun gab – ein leeres Eingabeverzeichnis endet
    mit Abbruch und Grund, nicht mit Exit 0 (D-097).
    """
    result = runner.invoke(app, ["run", "--input", str(tmp_path), "--out", str(tmp_path)])
    assert result.exit_code == EXIT_ABORTED
    assert "Keine Exportdateien" in result.output
