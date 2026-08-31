# Sprint 5 (vorgezogen) – UI-Prototyp

Läuft parallel zur Engine in einem eigenen Worktree (`~/projects/mdq-ui`, Branch `ui-proto`).
Arbeitsbereich **ausschließlich** `ui/`. Notizen, Entscheidungen und Schema-Rückmeldungen in
`ui/NOTES.md` (nicht in `docs/DECISIONS.md` – das übernimmt der Merge).

## Ziel

Ein klickbarer Prototyp, der Findings-JSON lädt und die drei Kern-Screens zeigt: Dashboard,
Findings-Explorer nach Aktionstyp, Review-Karte mit Evidenz-Panel – plus Dubletten-Vergleich
und Belegpaar-Ansicht. Kein Backend, keine Auth, keine Persistenz außer In-Memory + Export.
Das UI kennt nur `logic/finding.schema.json`; was die Engine liefert, ist ihm egal.

Der Prototyp dient drei Zwecken: (1) Test mit zwei Buchhaltern – Metrik: Zeit pro Entscheidung
unter 60 Sekunden, ohne Rückfrage; (2) Rückmeldung ans Schema, welche Felder fehlen;
(3) Vorführbarkeit. Das Design bleibt, der Code ist austauschbar.

## Stack (aus CLAUDE.md)

Vite + React + TypeScript + Tailwind + shadcn/ui. Dazu: TanStack Table, lucide-react,
js-yaml (nur im Build-Skript), vitest für Formatierer/Reducer. Kein Router-Framework,
kein State-Framework – `useReducer` reicht. Node ≥ 20 (falls nicht vorhanden: `nvm`).

## Datenfluss

- `ui/scripts/build-data.mjs`: liest `../logic/examples/findings/*.yaml`, validiert grob
  (Pflichtfelder), schreibt `ui/public/data/findings.json` und `ui/public/data/run.json`
  (`{run_id, data_as_of, engine_version, pack_version, tables_loaded: 0, company_codes: []}`
  aus den Findings abgeleitet). Läuft in `npm run dev`/`build` automatisch vor.
- Im UI zusätzlich „Findings-Datei laden" (Datei-Auswahl, JSON): damit lädt später
  `runs/<run_id>/findings.json` der Engine ohne Rebuild.
- Entscheidungen (übernehmen/ablehnen/zuweisen) leben im Reducer und lassen sich als
  `decisions.json` exportieren (`[{finding_id, action, reason_code, reason, by, at}]`).

## Design-Leitlinien (CONCEPT.md Abschnitt 9)

Ruhig, dicht, neutral. Monospace für Schlüssel, Belegnummern, Beträge. Schwere-Farben nur
als kleine Badges, keine farbigen Flächen. Detail als rechte Drawer, kein Seitenwechsel.
Deutsche Beschriftungen, deutsche Zahlformate (`32.000,00 €`, Datum `28.08.2026`).
Datenstand-Banner oben auf jedem Screen: „Stand 28.08.2026 · Lauf demo-2026-08-30 ·
Engine 0.1.0 · Regelpaket 0.1". Tastatur-first: `J`/`K` nächstes/vorheriges Finding,
`A` übernehmen, `R` ablehnen, `Z` zuweisen, `Esc` Drawer schließen, `/` Suche.
Vokabular strikt aus `docs/GLOSSARY.md`: Finding, Stufe, Schadensklasse, Ist, Soll,
Quellenlage, Evidenz, Euro-Wirkung, Aktionstyp.

## Aufgaben (je Aufgabe: Plan → Freigabe → Umsetzung → `npm run lint && npm run test && npm run build` → Commit)

### 1. Bootstrap + Datenmodell
- Vite-Projekt in `ui/`, Tailwind, shadcn/ui initialisiert (Button, Badge, Sheet/Drawer, Tabs, Table, Dialog, Tooltip, Select, Input).
- `ui/src/types/finding.ts`: TypeScript-Typen, aus `logic/finding.schema.json` abgeleitet (manuell oder per `json-schema-to-typescript` als Dev-Dependency). Enums als Union-Types.
- `ui/scripts/build-data.mjs` wie oben; `npm run dev` zeigt „6 Findings geladen".
- `ui/src/lib/format.ts`: `formatEur("32000.00") → "32.000,00 €"`, `formatDate("2026-08-28") → "28.08.2026"`, `formatKey` (Monospace-Komponente). vitest-Tests dafür.
- Akzeptanz: `npm run dev` startet, `npm run build` sauber, Tests grün, `ui/NOTES.md` angelegt.

### 2. App-Rahmen + Datenstand-Banner + Findings-Explorer
- Layout: schmale linke Navigation (Dashboard, Findings, Regeln), Datenstand-Banner, Inhalt.
- Findings-Explorer: Tabs nach Aktionstyp (Massenänderung / Review / Entscheidung / Prozess) mit Zählern; Tabelle (TanStack) mit Spalten: Stufe, Schwere, SK, Seite, Regel, Geschäftspartner (bp_key mono + display_name), Titel, Euro-Wirkung (rechtsbündig), Status. Sortierung Standard: Euro-Wirkung absteigend, dann Schwere.
- Filter: Seite, Kategorie, Schwere, Stufe, Buchungskreis, Status; Volltextsuche über bp_key, display_name, Titel, Regel-ID.
- Zeile klicken oder `Enter` öffnet die Review-Karte (Aufgabe 3) als Drawer.
- Akzeptanz: alle sechs Beispiele erscheinen in den richtigen Tabs; Filter kombinierbar; Sortierung stabil.

### 3. Review-Karte (der Kern)
Aufbau von oben nach unten, exakt in dieser Reihenfolge:
1. **Kopf:** display_name + bp_key (mono), Regel-ID + Version, Badges Stufe / Schwere / Schadensklasse / Aktionstyp, Euro-Wirkung groß rechts, Buchungskreis.
2. **Ist | Soll nebeneinander:** links `source_table.source_field` (mono) + `current.value` + `current.display`; rechts `proposed.value/display` + Quellenlage (`source_summary`) als Satz. Kein Soll → rechts der Hinweis „Kein Soll ermittelbar – Entscheidung/Prüfung" und bei `proposed.options` die Optionen als wählbare Karten mit Konsequenz.
3. **Evidenz-Panel:** je Eintrag eine Karte: Quellentyp (Label aus einer Map: vies → „VIES", duplicate_record → „Dublette", payment_run → „Zahllauf" …), Referenz (mono), Wert, Datum, Übereinstimmung (grün ✓ / rot ✗) und Notiz. Widersprüche oben.
4. **Euro-Wirkung:** Betrag + `formula` wörtlich + `netted_against`, wenn vorhanden.
5. **Warum** und **Wenn falsch:** zwei kurze Absätze, `if_wrong` optisch als Warnung bei Schadensklasse 1.
6. **Wie beheben:** Transaktion (mono), Pfad, Feld, Schritte als nummerierte Liste, Kennzeichen „massenänderungsfähig".
7. **Relevanz:** offene Posten, 12-Monats-Volumen, letzte Aktivität.
8. **Aktionen:** Übernehmen (`A`), Ablehnen (`R`, öffnet Dialog: reason_code Pflicht aus `intentionally_separate | data_correct | not_relevant | accepted_risk`, Freitext optional), Zuweisen (`Z`, Name), Später. Nach jeder Aktion springt die Karte zum nächsten offenen Finding (`J`).
- Schadensklasse 1: Aktion „Übernehmen" ist deaktiviert mit Tooltip „Bankdaten: Vier-Augen erforderlich – nur Review".
- Akzeptanz: alle sechs Beispiele vollständig dargestellt ohne leere Abschnitte (leere Abschnitte werden ausgeblendet, nicht als „–" gezeigt); Tastaturfluss durch alle sechs in unter 60 Sekunden.

### 4. Dubletten-Vergleich (category = duplicate)
- Statt Ist|Soll: Spalten je Konto aus `entity.bp_key` + `entity.related_bp_keys`; Zeilen: Name, Straße, PLZ/Ort, Land, USt-ID, IBAN, Zahlungsbedingung, offene Posten, letzte Zahlung. Gleiche Werte grau, abweichende hervorgehoben. Match-Gründe (aus `evidence` mit source_type model) als Chips über der Tabelle. Führendes Konto (aus `proposed.value`) mit Krone markiert.
- **Wichtig:** Die Beispiel-Findings enthalten die Vergleichswerte nur als Text in `current.display`. Für die Vergleichstabelle braucht das UI strukturierte Datensätze. Vorschlag für `ui/NOTES.md`: Schema-Erweiterung `entity.records: [{bp_key, fields: {name1, street, postal_code, city, country, vat_id, iban_masked, payment_terms, open_items_eur, last_activity_on}}]`. Bis dahin: `current.display` an ` | ` splitten und best-effort darstellen, klar als Platzhalter gekennzeichnet.
- Akzeptanz: F-002 zeigt zwei Spalten mit hervorgehobenen Unterschieden und drei Match-Chips.

### 5. Belegpaar-Ansicht (category = leakage mit `entity.documents`)
- Zwei Belegkarten nebeneinander aus `entity.documents` + `evidence`: Belegnummer, Datum, Referenz, Betrag. Darunter der Fuzzy-Grund (aus `source_summary`) und der Netting-Nachweis (Evidenz mit note „Netting-Prüfung" o. ä.).
- Akzeptanz: F-003 vollständig, F-005 (Skonto, ohne Belege) fällt sauber auf die normale Karte zurück.

### 6. Dashboard
- Kacheln: Findings gesamt, davon offen; Euro-Wirkung gesamt und je Kategorie; Verteilung nach Stufe; Top-10 nach Euro-Wirkung (klickbar → Karte).
- „Score" nur als Platzhalter-Kachel mit Text „ab Sprint 4" – keine erfundene Zahl.
- Akzeptanz: Zahlen stimmen mit den sechs Beispielen überein (Euro-Wirkung Summe = 32.000 + 8.930 + 4.812,40 + 27.300 = 73.042,40 €).

### 7. Stichproben-Freigabe + Export
- Im Tab Massenänderung: Gruppierung nach Regel; Button „Stichprobe prüfen" zeigt bis zu 10 zufällige Findings der Gruppe nacheinander (fester Seed, damit reproduzierbar); nach Bestätigung aller werden alle Findings der Gruppe auf `in_progress` gesetzt, die Stichprobe wird in der Export-Datei als `sample_reviewed: [ids]` festgehalten. (Korrektur 2026-08-31: hier stand `done`. Die Freigabe ist eine Entscheidung, keine Umsetzung – `done` gehört an die Rückmeldung aus SAP, nicht an den Klick im UI. Die Einzelentscheidung „Übernehmen" setzt aus demselben Grund `in_progress`.)
- Export `decisions.json` und Bereinigungsliste CSV (`bp_key;company_code;source_table;source_field;current;proposed;tier;rule_id`) für die Massenänderung.
- Akzeptanz: mit den Beispielen gibt es keine Stufe-A-Gruppe → Leerzustand mit Erklärung; Export funktioniert für Review-Entscheidungen.

## Definition of Done Sprint 5
- Alle sieben Aufgaben, `npm run lint`, `npm run test`, `npm run build` sauber.
- `ui/NOTES.md` enthält: getroffene UI-Entscheidungen, offene Fragen, **Schema-Rückmeldungen** (mindestens: `entity.records` für Dubletten; alles Weitere, was beim Bauen auffiel).
- Ein Testlauf mit zwei Buchhaltern protokolliert: Zeit pro Entscheidung, Rückfragen, Missverständnisse – Ergebnis in `ui/NOTES.md`.
- Merge-Vorbereitung: Branch `ui-proto` rebased auf `main`; die Schema-Rückmeldungen werden **nicht** vom UI-Worktree aus ins Schema geschrieben, sondern als Aufgabe an die Engine-Session übergeben.

## Nicht in diesem Sprint
Backend, Auth, Persistenz (außer In-Memory/Export), Score-Berechnung, Delta zwischen Läufen,
Regel-Konfiguration, Mehrsprachigkeit. Kein Einsatz von localStorage für Entscheidungen
(Export ist der Weg, damit nichts unbemerkt im Browser liegen bleibt).
