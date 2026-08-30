# Sprint 1 – Wahrheit definieren + Engine-Fundament

Ziel: Am Ende des Sprints validiert die Engine Findings gegen das Schema, lädt Regeln mit
YAML-Kopf, führt sie gegen das kanonische Schema aus und der Loader liest alle fünf
Encoding-Samples identisch ein. Dazu 30 Beispiel-Findings (Victor) und Regelkatalog freigegeben.

## Aufgaben für Claude Code (in dieser Reihenfolge, je Aufgabe Plan → Freigabe → Umsetzung → Tests → Commit)

### 1. Projekt-Bootstrap
- `uv sync` lauffähig; Paket `engine/mdq/` mit `__init__.py`, `cli.py` (Typer: `mdq validate`, `mdq rules list`, später `mdq run`).
- `[project.scripts] mdq = "mdq.cli:app"` in `pyproject.toml` ergänzen, inkl. Build-Konfiguration (hatchling, `packages = ["engine/mdq"]`).
- `engine/tests/` mit `conftest.py` (DuckDB-In-Memory-Fixture, das `logic/schema/canonical.sql` lädt).
- Akzeptanz: `uv run pytest` läuft (auch wenn erst 1 Test), `uv run ruff check .` sauber.

### 2. Schema-Validierung
- `mdq/findings.py`: `validate_finding(dict) -> list[str]` mit jsonschema Draft 2020-12 + FormatChecker.
- Test: alle Dateien in `logic/examples/findings/*.yaml` sind valide. Test: ein bewusst kaputtes Finding (damage_class 1 + tier A) wird abgelehnt.
- `mdq validate logic/examples/findings/` als CLI.

### 3. Regel-Loader
- `mdq/rules.py`: liest `logic/rules/*.rule.sql`, parst den YAML-Kopf zwischen `/* ---` und `--- */`, prüft Pflichtfelder (id, version, side, category, severity, damage_class, default_tier, default_action_type, requires_tables, plain_logic, why, if_wrong, remediation, tests) und die Invariante `damage_class == 1 → default_tier != 'A'`.
- Test: `_TEMPLATE.rule.sql` wird übersprungen, die drei Beispielregeln laden, ein Kopf ohne `plain_logic` wirft einen klaren Fehler.
- `mdq rules list` zeigt ID, Version, Seite, Kategorie, Stufe.

### 4. Regel-Ausführung (Minimal)
- `mdq/executor.py`: führt das SQL einer Regel gegen eine DuckDB-Verbindung aus, prüft, dass die Pflichtspalten des Ausgabe-Vertrags (`logic/rules/README.md`) vorhanden sind, und baut daraus Findings (finding_id = `F-` + sha1(rule_id|bp_key|company_code|source_table|source_field|current_value|finding_key)[:12] – `company_code` und `finding_key` ergänzt, weil eine Regel mehrere Findings je BP liefern kann; siehe D-027, why/if_wrong/title mit `params` gefüllt, Defaults aus dem Kopf, `relevance` aus `bp_relevance` wenn vorhanden).
- Test: mit einer handvoll INSERTs (wie im Kommentar der Beispielregeln) liefert jede der drei Regeln genau 1 Finding, das gegen das Schema valide ist. Test: gleiche Daten zweimal → identische finding_ids und Reihenfolge.

### 5. Loader für SE16N-Exports (nur Encoding/Format, noch kein Mapping)
- `mdq/loader.py`: erkennt Encoding (UTF-8, UTF-8-BOM, UTF-16 mit BOM, CP1252-Fallback), Trenner (Tab, Semikolon), Quoting; liest in eine DuckDB-Tabelle `raw_<TABELLE>` mit allen Spalten als TEXT; gibt `{rows, encoding, delimiter, sha256}` zurück.
- Test: die vier `KNA1_*`-Dateien in `testdata/encoding_samples/` ergeben zeilen- und zellengleiche Tabellen (Umlaute intakt, führende Nullen intakt).
- `mdq/formats.py`: `parse_amount("1.234,56-") == Decimal("-1234.56")`, `parse_amount("1234.56")`, `parse_date("20260830")`, `parse_date("30.08.2026")` – mit Tests aus `BSID_formats.txt`.
- Nicht parsebare Werte → Eintrag in `reject`, kein Abbruch, kein stummes NULL.

### 6. Run-Report (Skelett)
- `mdq/report.py`: Textausgabe (rich): geladene Dateien mit Encoding/Zeilen, Rejects je Stufe, Regeln ausgeführt/übersprungen (fehlende Tabellen), Findings je Regel.

## Aufgaben für Victor (parallel, fachlich)
- 24 weitere Beispiel-Findings in `logic/examples/findings/` (Liste im dortigen README), jeweils `uv run mdq validate` grün.
- `logic/rules/CATALOG.md`: offene Fragen beantworten, Status `draft → spec` für die 10 Regeln, die in Sprint 3 zuerst gebaut werden (Klartext + Testfälle im Kopf).
- Extraktionsanleitung gegenlesen: fehlen Felder, stimmen Transaktionen?

## Definition of Done Sprint 1
- Alle Tests grün, Ruff sauber, `mdq validate`, `mdq rules list` funktionieren.
- `docs/DECISIONS.md` ergänzt (mindestens: Paketlayout, Encoding-Erkennung, finding_id-Bildung).
- `docs/SESSION_LOG.md` je Session gepflegt, Commits vorhanden.
- 30 Beispiel-Findings valide, 10 Regeln im Status `spec`.

## Nicht in Sprint 1
Mapping SAP → kanonisch (Sprint 3), Demo-Mandant-Generator (Sprint 2), Dubletten (Sprint 4),
Euro-Wirkung (Sprint 4), UI (Sprint 5), Betrieb/Lizenz/Updates/Auth (spätere Sprints, D-063).

**Erkennung der Dezimalnotation je Datei (Sprint 3):** `parse_amount` beherrscht in Sprint 1
beide Schreibweisen auf Wert-Ebene und lehnt mehrdeutige Werte wie `1.234` ab. Sprint 3
ermittelt die Notation je Datei aus den eindeutigen Werten, wendet sie auf die mehrdeutigen
an und bietet den Laufparameter `--decimal-notation de|iso` für Dateien ohne eindeutigen
Wert; ohne beides bleibt es beim Reject. Siehe D-035.
