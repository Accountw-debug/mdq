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

- **2026-08-30 · Tailwind v4 statt v3.** Grund: der aktuelle `shadcn`-CLI initialisiert
  gegen v4 (`@tailwindcss/vite`, Theme über CSS-Variablen in `src/index.css`, keine
  `tailwind.config.js`); v3 hieße gegen den Strom des Generators arbeiten.
  Verworfen: Tailwind v3 mit klassischer Config.
- **2026-08-30 · Findings-Typen von Hand geschrieben** (`src/types/finding.ts`) statt
  `json-schema-to-typescript`. Grund: das Schema lebt von drei `allOf`-Bedingungen
  (Schadensklasse 1 nie Stufe A; Stufe A/B brauchen ein Soll; `mass_change` nur Stufe A),
  die ein Generator zu breiten Typen verflacht. Driftschutz: `src/types/finding.enums.test.ts`
  gleicht alle neun Enum-Listen zur Testzeit gegen `logic/finding.schema.json` ab (nur lesend).
  Verworfen: Generator als Dev-Dependency.
- **2026-08-30 · Beträge auch im Formatierer als String.** `src/lib/format.ts` arbeitet
  rein string-basiert (Regex + Dreiergruppierung); gerechnet wird über `bigint`-Cents
  (`parseCents`/`sumEur`). Kein `Number`, kein `parseFloat`, keine Rundung. Grund:
  CLAUDE.md Regel 2 endet nicht an der UI-Grenze. Verworfen: `Intl.NumberFormat`, weil
  es den String durch einen `number` schleusen müsste.
- **2026-08-30 · Kein Locale- und kein Zeitzonen-Bezug in der Formatierung.** `formatDate`
  und `formatDateTime` zerlegen den ISO-String per Regex, ohne `Date`. Zeitstempel werden
  als UTC ausgewiesen („30.08.2026 09:15 UTC"). Grund: Regel 9 – derselbe Lauf muss auf
  jedem Rechner gleich aussehen; der Zeitstempel gehört zum Lauf, nicht zum Betrachter.
- **2026-08-30 · `formatKey` wurde zur Komponente `src/components/Key.tsx`.** Die Spec
  nennt es „Monospace-Komponente"; als JSX kann es nicht in die `.ts`-Datei `format.ts`,
  die rein und testbar bleiben soll.
- **2026-08-30 · `tables_loaded: 0` im abgeleiteten `run.json`.** Das UI kennt die
  Ladeschicht nicht und erfindet keine Zahl; die echte liefert später `runs/<run_id>/run.json`
  der Engine. `company_codes` wird dagegen aus `entity.company_code` abgeleitet
  (eindeutig, sortiert → `["1000","2000"]`).
- **2026-08-30 · Betrag und Währungszeichen mit gewöhnlichem Leerzeichen** („32.000,00 €"),
  nicht mit geschütztem. Grund: so steht es in der Spec und ist in Tests und Diffs sichtbar;
  gegen Umbruch hilft CSS. Offen, falls im Buchhalter-Test störend.
- **2026-08-30 · Vitest ohne DOM-Umgebung** (`environment: 'node'`). Getestet werden laut
  Spec Formatierer und später der Reducer – beides reine Funktionen. Verworfen: jsdom +
  Testing Library als zusätzliche Abhängigkeiten.

## Offene Fragen an die Engine-Session (`main`)

- **`created_at` immer UTC mit `Z`?** `formatDateTime` weist Zeitstempel als UTC aus und
  lehnt Offsets wie `+02:00` ab. Wenn die Engine auch Offsets schreiben kann, sag Bescheid –
  dann braucht der Formatierer eine Regel dafür.
- **`run.json` neben `findings.json`?** Der Prototyp leitet Lauf-Kopf, Datenstand und
  Buchungskreise aus den Findings ab. Schöner wäre, wenn die Engine `runs/<run_id>/run.json`
  mitschreibt (mit echtem `tables_loaded`). Kein Blocker.
- **Schema-Rückmeldung `entity.records` für Dubletten** folgt in Aufgabe 4, sobald der
  Vergleich gebaut ist.

## Session-Notizen

Format: `Datum · Ziel · Ergebnis · Nächster Schritt`

- **2026-08-30 · Branch angelegt.** Worktree `../mdq-ui` auf `ui-proto` von `main` bei
  `0bff445`. Noch kein UI-Code. Nächster Schritt: Sprint 5 laut `docs/specs/`, bis dahin
  Vorarbeit am Findings-Vertrag möglich.
- **2026-08-30 · Aufgabe 1 (Bootstrap + Datenmodell).** Vite 8 + React 19 + TypeScript 6 +
  Tailwind v4 + shadcn/ui (Preset `radix-nova`, Basisfarbe neutral) in `ui/` aufgesetzt;
  Komponenten Button, Badge, Sheet, Tabs, Table, Dialog, Tooltip, Select, Input.
  `src/types/finding.ts`, `src/lib/format.ts`, `src/components/Key.tsx`,
  `scripts/build-data.mjs` (6 Findings → `public/data/{findings,run}.json`).
  29 Tests grün, `npm run lint` und `npm run build` ohne Befund.
  Nächster Schritt: Aufgabe 2 – App-Rahmen, Datenstand-Banner, Findings-Explorer.
