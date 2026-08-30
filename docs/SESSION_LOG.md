# Session-Log

Format je Session: Datum · Ziel · Ergebnis · Offen/Nächster Schritt (max. 3 Zeilen)

- **2026-08-30 · Repo-Start.** Starter-Struktur, CLAUDE.md, Konzept, Schema, Regel-Template, Mapping, Wörterbücher, Beispiel-Findings, Encoding-Samples angelegt. Nächster Schritt: Sprint 1 laut `docs/specs/SPRINT-1.md`.
- **2026-08-30 · Sprint 1, Aufgabe 1: Projekt-Bootstrap.** Paket `engine/mdq/` (Pfad-Konstanten, Typer-CLI mit `version` und Stubs für `validate`, `rules list`, `run`), hatchling-Build und Entry Point in `pyproject.toml`, `engine/tests/conftest.py` mit DuckDB-In-Memory-Fixture für `logic/schema/canonical.sql`, 3 Bootstrap-Tests.
  Ergebnis: `uv run pytest` 3 passed, `uv run ruff check .` sauber, `uv run mdq version` läuft. Entscheidungen D-011 bis D-014 ergänzt, `uv.lock` eingecheckt.
  Nächster Schritt: Sprint 1, Aufgabe 2 – Schema-Validierung (`mdq/findings.py`, `mdq validate`).
