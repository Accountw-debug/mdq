# MDQ – Finance Master Data & Leakage Check

Prüft Debitoren- und Kreditorenstammdaten (SAP ECC/S4) auf Qualität, Dubletten und
Euro-Wirkung (Doppelzahlungen, Skontoverluste, Unapplied Cash) und liefert pro Finding
Ist, Soll, Quellen, Konfidenz-Stufe und SAP-Handlungsanweisung.

Lies vor jeder Arbeit: `docs/CONCEPT.md`, `docs/GLOSSARY.md`, `docs/DECISIONS.md`,
die aktuelle Spec unter `docs/specs/` und den letzten Eintrag in `docs/SESSION_LOG.md`.

## Was dieses Repo ist

| Ordner | Rolle | Sorgfalt |
|---|---|---|
| `logic/` | Technologieunabhängiger Asset: Schema, Regeln, Mappings, Wörterbücher, Beispiel-Findings | Höchste – bleibt auch bei Neubau der Engine |
| `engine/` | Prototyp-Engine (Python + DuckDB). Kann später neu gebaut werden | Sauber, aber pragmatisch |
| `ui/` | Prototyp-UI (Vite + React + TS + Tailwind + shadcn). Liest **nur** Findings-JSON | Design zählt, Code ist austauschbar |
| `testdata/` | Synthetischer Demo-Mandant, Encoding-Samples, erwartete Findings | **Niemals echte Daten** |
| `docs/` | Konzept, Entscheidungen, Glossar, Specs, Session-Log | Immer aktuell halten |

## Stack (nur mit Eintrag in `docs/DECISIONS.md` erweitern)

- Python ≥ 3.12 mit `uv`; DuckDB; PyYAML; jsonschema; pytest; ruff; rapidfuzz; python-stdnum; schwifty
- UI: Vite + React + TypeScript + Tailwind + shadcn/ui
- **Nicht:** Postgres, Docker, Auth, Cloud, ORM, Pandas-Pipelines (Transformationen in DuckDB-SQL)

## Nicht verhandelbare Regeln

1. **Erwartete Testergebnisse werden NIE angepasst, um Tests grün zu bekommen.** Das gilt für `testdata/expected/`, die Testfälle in Regelköpfen und `logic/examples/`. Wirkt ein erwartetes Ergebnis falsch: stoppen, Begründung schreiben, Victor fragen.
2. **Beträge sind `DECIMAL(15,2)`, nie float.** Währung steht immer neben dem Betrag. Schlüssel (`KUNNR`, `LIFNR`, `BELNR`, `BUKRS`) sind Text, führende Nullen bleiben erhalten.
3. **Rohdaten werden nie verändert.** Pipeline: `raw → staged → canonical → findings`. Jede Stufe ist eine eigene DuckDB-Tabelle.
4. **Nichts wird stumm verworfen.** Nicht parsebare Zeilen → Tabelle `reject` mit Grund. Unbekannte Spalte im Export → Fehler mit Spaltenname.
5. **Eine Regel = eine Datei** `logic/rules/<ID>.rule.sql` mit YAML-Kopf. Regeln lesen nur das kanonische Schema, nie Raw/Staged.
6. **Jedes Finding wird gegen `logic/finding.schema.json` validiert.** Ungültiges Finding = Lauf schlägt fehl.
7. **Keine externen Aufrufe ohne expliziten Schalter** (`--enrich vies`). In Tests immer aus.
8. **Logs, Fehlermeldungen und Tests enthalten keine Geschäftspartnerdaten** (Namen, IBAN, Adressen). Nur Schlüssel und Regel-IDs.
9. **Determinismus:** gleicher Input → identische Findings (gleiche IDs, gleiche Reihenfolge). Keine Zufälligkeit ohne festen Seed.
10. **Klartext-Logik im Regelkopf muss dem SQL entsprechen.** Bei jeder SQL-Änderung Klartext mitprüfen.
11. **Schadensklasse 1 (Bankdaten) wird nie Stufe A.** Auch nicht per Policy. Siehe `docs/CONCEPT.md`.

## Arbeitsweise

- Aufgaben, die mehr als eine Datei ändern: erst Plan vorschlagen, Freigabe abwarten, dann umsetzen.
- Kleine Schritte: eine Regel, eine Tabelle, ein Screen pro Aufgabe.
- Nach jeder Aufgabe `uv run pytest` ausführen und das Ergebnis zeigen.
- Architekturentscheidungen sofort in `docs/DECISIONS.md` (Datum, Entscheidung, Grund, verworfene Alternativen).
- Am Ende jeder Session: drei Zeilen in `docs/SESSION_LOG.md`, Commit mit sprechender Message.
- Begriffe ausschließlich aus `docs/GLOSSARY.md` verwenden.
- Bei fachlichen Unklarheiten (Was ist eine Dublette? Welche Schwere?) nicht raten, sondern fragen.

## Definition of Done – vor jedem "fertig" prüfen und ausdrücklich bestätigen

- [ ] `uv run pytest` grün, inklusive Demo-Mandant-Regression
- [ ] `uv run ruff check .` ohne Befunde
- [ ] Kein float für Beträge, keine stillen `except:`-Blöcke
- [ ] Neue/geänderte Regel: Testfälle (trifft / trifft nicht / Grenzfall) vorhanden, Klartext aktuell
- [ ] Run-Report zeigt keine unerklärten Rejects
- [ ] Findings valide gegen Schema
- [ ] Keine Geschäftspartnerdaten in Logs oder Tests
- [ ] `docs/DECISIONS.md` und `docs/SESSION_LOG.md` aktualisiert
- [ ] Commit erstellt

## Befehle

```
uv sync                                     # Abhängigkeiten
uv run pytest                               # alle Tests
uv run ruff check .                         # Lint
uv run mdq run --input testdata/demo_mandant --out runs/   # Lauf (ab Sprint 3)
```
