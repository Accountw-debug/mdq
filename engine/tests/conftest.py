"""Gemeinsame Fixtures der Engine-Tests."""

from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest

from mdq import CANONICAL_SCHEMA, LOGIC_DIR, PROJECT_ROOT


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Wurzel des Repos."""
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def logic_dir() -> Path:
    """Verzeichnis logic/ – Schema, Regeln, Mappings, Woerterbuecher."""
    return LOGIC_DIR


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
