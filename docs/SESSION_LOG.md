# Session-Log

Format je Session: Datum · Ziel · Ergebnis · Offen/Nächster Schritt (max. 3 Zeilen)

- **2026-08-30 · Repo-Start.** Starter-Struktur, CLAUDE.md, Konzept, Schema, Regel-Template, Mapping, Wörterbücher, Beispiel-Findings, Encoding-Samples angelegt. Nächster Schritt: Sprint 1 laut `docs/specs/SPRINT-1.md`.
- **2026-08-30 · Sprint 1, Aufgabe 1: Projekt-Bootstrap.** Paket `engine/mdq/` (Pfad-Konstanten, Typer-CLI mit `version` und Stubs für `validate`, `rules list`, `run`), hatchling-Build und Entry Point in `pyproject.toml`, `engine/tests/conftest.py` mit DuckDB-In-Memory-Fixture für `logic/schema/canonical.sql`, 3 Bootstrap-Tests.
  Ergebnis: `uv run pytest` 3 passed, `uv run ruff check .` sauber, `uv run mdq version` läuft. Entscheidungen D-011 bis D-014 ergänzt, `uv.lock` eingecheckt.
  Nächster Schritt: Sprint 1, Aufgabe 2 – Schema-Validierung (`mdq/findings.py`, `mdq validate`).
- **2026-08-30 · Sprint 1, Aufgabe 2: Schema-Validierung.** `mdq/findings.py` (Draft-2020-12-Validierung, eigener `date-time`-Checker, YAML-Loader ohne Timestamp-Resolver, YAML+JSON, Duplikatprüfung) und `mdq validate` umgesetzt; die drei Schema-Invarianten werden mit ihrem Klartext gemeldet.
  Ergebnis: `uv run pytest` 33 passed, `uv run ruff check .` sauber, `mdq validate logic/examples/findings/` grün (6/6). Entscheidungen D-015 bis D-020 ergänzt.
  Nächster Schritt: Sprint 1, Aufgabe 3 – Regel-Loader (`mdq/rules.py`, `mdq rules list`).
- **2026-08-30 · Sprint 1, Aufgabe 3: Regel-Loader.** `mdq/rules.py` (YAML-Kopf parsen, 14 Pflichtfelder, Wertebereiche, vier Invarianten, Sammelmeldung, Vorlagen übersprungen) und `mdq rules list` mit Hinweis auf leere Testfälle umgesetzt; `requires_tables` werden gegen das kanonische Schema geprüft.
  Ergebnis: `uv run pytest` 68 passed, `uv run ruff check .` sauber, `mdq rules list` zeigt die drei Regeln. D-021 bis D-024 ergänzt; im Katalog AP-CON-003 auf Stufe C und AR-HYG-001/AP-HYG-001 auf `decision` korrigiert.
  Nächster Schritt: Sprint 1, Aufgabe 4 – Regel-Ausführung (`mdq/executor.py`), inkl. der offenen Frage zu `mass_change` bei den beiden HYG-Zeilen.
