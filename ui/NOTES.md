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
- **2026-08-30 · TanStack Table v9 statt v8.** `npm install @tanstack/react-table` liefert
  9.2.4 mit neuer API (`tableFeatures({})`, `useTable`, `table.FlexRender`); die aus v8
  bekannten `useReactTable`/`getCoreRowModel` gibt es nur noch als `legacy`-Einstieg.
  Genutzt wird der Kern-Funktionssatz ohne Sortier-, Filter- oder Paginierungs-Feature –
  das erledigen eigene Funktionen. Verworfen: Pin auf v8, verworfen: der `legacy`-Pfad.
- **2026-08-30 · Sortieren, Filtern und Suchen bleiben eigene reine Funktionen**
  (`src/lib/select-findings.ts`), nicht Sache der Tabelle. Grund: Regel 9 – die
  Reihenfolge ist so im Test festgenagelt statt vom Bibliotheksverhalten abhängig.
  Beträge werden über `parseCents` als `bigint` verglichen, nie über `Number`. Jede
  Sortierung endet auf Schwere absteigend und dann `finding_id`, damit Gleichstand nie
  dem Zufall überlassen bleibt. Findings ohne `impact_eur` zählen als 0.
- **2026-08-30 · Filter einwertig je Dimension** („Alle" plus ein Wert), Dimensionen
  wirken als UND. Freigabe Victor. Grund: ruhige Leiste, reicht für die Fragen der
  Buchhalter. Verworfen: Mehrfachauswahl je Dimension.
- **2026-08-30 · Auswahl wird bei Tab-, Filter- und Suchwechsel zurückgesetzt.** Grund:
  eine Tastaturmarke auf einer ausgeblendeten Zeile ist unsichtbar; `J` beginnt danach
  wieder oben. Beim Sortieren und beim Schließen des Drawers bleibt sie stehen.
- **2026-08-30 · Deutsche Beschriftungen der Enum-Werte in `src/lib/labels.ts`.** Das
  Glossar nennt die Feldnamen, aber keine deutschen Wörter für die Werte. Die Kategorien
  folgen `docs/CONCEPT.md` Abschnitt 3 (Vollständigkeit/Validität/Konsistenz/Hygiene/
  Risiko); `duplicate` → „Dublette". **Offen: `leakage` → „Geldabfluss"** ist hier gesetzt
  und steht in keinem Dokument – bitte gegenlesen. `labels.test.ts` erzwingt, dass jede
  Enum-Konstante genau eine Beschriftung hat.
- **2026-08-30 · Explorer-Zustand liegt in `App.tsx`**, nicht im Explorer. Grund: Filter,
  Suche und Auswahl überleben so einen Wechsel auf Dashboard und zurück.
- **2026-08-30 · Rauchtest per `renderToStaticMarkup`** statt jsdom + Testing Library
  (`FindingsExplorer.render.test.tsx`, `vitest`-`include` um `*.test.tsx` erweitert).
  Er beantwortet, was Typprüfung und Reducer-Tests offenlassen: dass Zeilen, Beträge und
  Leerzustände wirklich im Markup ankommen. Grenze: Portale (Drawer, Select-Liste,
  Tooltip) rendert `renderToStaticMarkup` nicht – die Review-Karte prüft Aufgabe 3.
  Ergänzt die Entscheidung „Vitest ohne DOM-Umgebung", widerspricht ihr nicht: es bleibt
  bei `environment: 'node'` und ohne neue Abhängigkeit.
- **2026-08-30 · „Findings-Datei laden" liegt im Datenstand-Banner.** Freigabe Victor.
  Die Datei wird nur im Speicher gehalten (kein `localStorage`), der Lauf-Kopf wird wie
  im Build-Skript abgeleitet. Unbrauchbare Dateien brechen mit Grund ab statt halb zu
  erscheinen (Regel 4); die Meldungen nennen nur Feldnamen, Regel-IDs und `finding_id`,
  nie Geschäftspartnerdaten (Regel 8).

## Offene Fragen an die Engine-Session (`main`)

- **Schema-Rückmeldung `entity.records` für Dubletten** folgt in Aufgabe 4, sobald der
  Vergleich gebaut ist.
- **`title` ist im Schema optional, die Liste braucht es aber.** Die Findings-Tabelle hat
  eine Spalte Titel; fehlt er, steht dort „—". Vorschlag: `title` zur Pflicht machen
  (max. 120 Zeichen wie bisher beschrieben). Kein Blocker.
- **`entity.company_code` ist optional** – F-7b2e8c1d9a3f (Dublette) hat keinen. Das UI
  führt dafür den Filterwert „ohne Buchungskreis". Falls Dubletten-Findings künftig einen
  Buchungskreis bekommen sollen, sag Bescheid; erfunden wird hier keiner.

### Beantwortet

- **2026-08-30 · `created_at` immer UTC mit `Z`? – erledigt.** Ja: `created_at` kommt aus dem
  `RunContext` und ist immer UTC mit `Z` (D-028). Offsets wie `+02:00` treten nicht auf;
  `formatDateTime` darf sie weiter zurückweisen. Keine Änderung am Formatierer nötig.
- **2026-08-30 · `run.json` neben `findings.json`? – erledigt.** Ja: die Engine schreibt
  `runs/<run_id>/run.json` ab Sprint 3 neben `findings.json`. Das UI liest den Lauf-Kopf
  schon heute als eigene Datei (`RunInfo`), die echte Datei passt also ohne Codeänderung;
  `tables_loaded` ist dann echt statt `0`. `scripts/build-data.mjs` bleibt als Ersatz für
  den Prototyp, solange kein Lauf vorliegt.

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
- **2026-08-30 · Aufgabe 2 (App-Rahmen, Datenstand-Banner, Findings-Explorer).**
  `AppShell` mit schmaler Navigation (Findings ist gebaut, Dashboard und Regeln sind
  Platzhalter), Datenstand-Banner mit „Findings-Datei laden", Explorer mit Tabs nach
  Aktionstyp (0/4/1/1), sechs Filtern, Volltextsuche, TanStack-Tabelle, Sortierung
  Euro-Wirkung absteigend, Tastatur `J`/`K`/`Enter`/`Esc`/`/` und Review-Drawer als
  Rumpf. 99 Tests grün, `npm run lint` und `npm run build` ohne Befund.
  Nächster Schritt: Aufgabe 3 – die Review-Karte füllen.
