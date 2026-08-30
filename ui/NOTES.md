# UI-Notizen (Branch `ui-proto`)

Arbeitsnotizen der UI-Session. **Diese Datei ersetzt `docs/DECISIONS.md` für die Dauer
des Branches.** Beim Merge nach `main` werden die Einträge unter „Entscheidungen" von
Victor in `docs/DECISIONS.md` übernommen und bekommen dort ihre endgültige `D-NNN`-Nummer;
diese Datei wird dann geleert.

## Arbeitsvereinbarung

- **Nur `ui/` ändern.** `logic/`, `engine/`, `testdata/`, `docs/` und die Dateien im
  Wurzelverzeichnis gehören der Engine-Session auf `main`. Wird dort etwas gebraucht:
  hier als offene Frage notieren, nicht selbst ändern.
- **`docs/DECISIONS.md` und `docs/SESSION_LOG.md` in diesem Branch nicht anfassen.**
  Sonst gibt es beim Merge Konflikte in genau den zwei Dateien, die die Projekthistorie
  tragen. Alles hier hinein.
- Es gilt weiterhin die gesamte `CLAUDE.md`, insbesondere: keine echten Daten (D-008),
  keine Geschäftspartnerdaten in Logs (Regel 8), Beträge nie als float (Regel 2),
  Begriffe aus `docs/GLOSSARY.md`.
- Die UI liest **ausschließlich** Findings-JSON (D-007). Der Vertrag ist
  `logic/finding.schema.json`; keine Annahme über die Engine, die dort nicht steht.
  Zum Ausprobieren dienen `logic/examples/findings/` – als JSON konvertierbar mit
  `uv run mdq validate` als Gegenprobe.
- Stack laut `CLAUDE.md`: Vite + React + TypeScript + Tailwind + shadcn/ui. Erweiterung
  nur mit Eintrag unter „Entscheidungen" hier.
- Gestaltungsleitlinien: `docs/CONCEPT.md`, Abschnitt 9 (Review-Karte als Kern, ruhig und
  dicht, Monospace für IDs und Beträge, Drawer statt Seitenwechsel, Datenstand-Banner).

## Entscheidungen (werden beim Merge nach `docs/DECISIONS.md` übernommen)

Format wie dort: `Datum · Entscheidung · Grund · Verworfene Alternativen`

- _(noch keine)_

## Offene Fragen an die Engine-Session (`main`)

- _(noch keine)_

## Session-Notizen

Format: `Datum · Ziel · Ergebnis · Nächster Schritt`

- **2026-08-30 · Branch angelegt.** Worktree `../mdq-ui` auf `ui-proto` von `main` bei
  `0bff445`. Noch kein UI-Code. Nächster Schritt: Sprint 5 laut `docs/specs/`, bis dahin
  Vorarbeit am Findings-Vertrag möglich.
