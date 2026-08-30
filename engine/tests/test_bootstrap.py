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


def test_validate_is_not_implemented_yet(tmp_path) -> None:
    result = runner.invoke(app, ["validate", str(tmp_path)])
    assert result.exit_code == EXIT_NOT_IMPLEMENTED
