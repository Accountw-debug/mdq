"""Bootstrap: Paket importierbar, Schema-Fixture laedt, CLI-Geruest antwortet."""

from typer.testing import CliRunner

from mdq import __version__
from mdq.cli import EXIT_NOT_IMPLEMENTED, app

runner = CliRunner()


def test_canonical_schema_is_loaded(canonical_db) -> None:
    rows = canonical_db.execute("SELECT table_name FROM duckdb_tables()").fetchall()
    tables = {row[0] for row in rows}
    assert {"business_partner", "reject", "fi_item", "run_meta"} <= tables


def test_version_command_succeeds() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_stub_command_exits_non_zero(tmp_path) -> None:
    """Ein noch nicht umgesetzter Befehl meldet nie einen leeren Erfolg (D-013).

    Geprueft am letzten verbliebenen Stub `run` (Sprint 3); `validate` und `rules list`
    sind umgesetzt und werden in test_findings.py bzw. test_rules.py geprueft.
    """
    result = runner.invoke(app, ["run", "--input", str(tmp_path), "--out", str(tmp_path)])
    assert result.exit_code == EXIT_NOT_IMPLEMENTED
