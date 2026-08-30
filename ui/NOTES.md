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
  Risiko); `duplicate` → „Dublette". `leakage` → „Geldabfluss" ist hier gesetzt und steht in
  keinem Dokument; **am 2026-08-30 als Glossar-Rückmeldung an die Engine-Session (`main`)
  übergeben**, bis zu einer Antwort bleibt es bei „Geldabfluss". `labels.test.ts` erzwingt, dass jede
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
- **2026-08-30 · Aktion → Status: Übernehmen und Zuweisen setzen `in_progress`.**
  Freigabe Victor. „Übernehmen" heißt „freigegeben – Umsetzung offen", „Zuweisen" heißt
  „zugewiesen"; beide sind `in_progress`, nur der Text unterscheidet sie
  (`DECISION_STATUS_LABELS`, `StatusBadge` mit `label`). Ablehnen setzt `rejected`, mit
  Grund „Risiko akzeptiert" dagegen `accepted_risk`. **`done` vergibt das UI nie** – das
  entscheidet der nächste Lauf, in dem das Finding nicht mehr auftaucht. Verworfen:
  Übernehmen → `done` (behauptet eine Umsetzung, die im SAP noch aussteht).
- **2026-08-30 · Entscheidungen liegen als Überlagerung über den Findings.**
  `src/state/decisions.ts` hält `finding_id → Entscheidungssatz`; `applyDecisions` legt
  Status und `decision` über eine Kopie, die geladenen Findings bleiben unverändert
  (Analogie zu Regel 3). Das Ergebnis bleibt schemakonform: `decision` bekommt nur
  `by`, `at`, `reason`, `reason_code`. Aufgabe 7 exportiert die Map direkt.
- **2026-08-30 · `decision.at` kommt aus einer injizierbaren Uhr.** `createDecision(input, now)`
  – der Zeitstempel ist der einzige Wert im UI, der nicht aus den Daten folgt; im Test
  steht er fest (Regel 9). Verworfen: `new Date()` mitten im Rendering.
- **2026-08-30 · Bearbeiter steht im Datenstand-Banner, nicht in einem Dialog.**
  `decision.by` ist im Schema Pflicht, also wird der Name einmal je Sitzung eingetragen;
  ohne ihn sind Übernehmen, Ablehnen und Zuweisen gesperrt (mit Hinweis, „Später" bleibt
  frei). Nur im Speicher, kein `localStorage`. Verworfen: Namensabfrage beim ersten Klick
  (ein dritter Dialog für eine Angabe, die einmal gilt).
- **2026-08-30 · Die Review-Karte hängt in keinem Portal.** `ReviewCard` trägt Kopf,
  Abschnitte, Aktionen und die Tastatur; `ReviewDrawer` ist nur noch Sheet-Hülle mit
  zugänglichem Namen. Damit prüft `ReviewCard.render.test.tsx` alle sechs Beispiele mit
  `renderToStaticMarkup` – die in Aufgabe 2 notierte Grenze ist damit aufgehoben, ohne
  jsdom und ohne neue Abhängigkeit.
- **2026-08-30 · Optionen einer Entscheidung sind wählbar, und die Wahl wird festgehalten.**
  Ohne gewählte Option ist „Übernehmen" gesperrt (Tooltip „Erst eine der Optionen wählen"),
  mit Wahl steht sie als Grund im Entscheidungssatz („Option gewählt: …"). Die Spec nennt
  die Optionen „wählbar"; ohne Wirkung wäre die Wahl Dekoration.
- **2026-08-30 · „Später" schreibt nichts, und Entscheidungen sind zurücknehmbar.**
  „Später" springt nur zum nächsten offenen Finding. Zu jeder getroffenen Entscheidung
  steht „Zurücknehmen" auf der Karte – ohne Persistenz wäre ein Fehlgriff sonst endgültig.
- **2026-08-30 · Sprung nach der Entscheidung: `nextOpenId`.** Nächstes offenes Finding
  hinter der Marke, sonst das erste offene von oben, sonst schließt die Karte. Reine
  Funktion im Reducer, damit die Reihenfolge im Test steht und nicht im Klickverhalten.
- **2026-08-30 · `formatMoney(amount, currency)` statt `formatEur` überall dort, wo ein
  `impact_eur` gezeigt wird.** Die Währung steht im Finding und gehört neben den Betrag
  (Regel 2); unbekannte Währungen behalten ihren Code. Nur `formatEur` bliebe stumm falsch,
  sobald ein Lauf CHF liefert.
- **2026-08-30 · Die Drawer-Breite läuft über `--sheet-width`, nicht über `className`.**
  Die Breite steht in `sheet.tsx` als `data-[side=right]:sm:max-w-…`; ein `sm:max-w-3xl`
  am Aufruf trägt diese Varianten nicht, `tailwind-merge` sieht keinen Konflikt und lässt
  beide Klassen stehen – im erzeugten CSS gewinnt die Regel mit den Varianten, weil sie
  später steht. Die Review-Karte war deshalb 24rem breit statt der angeschriebenen 48rem.
  `sheet.tsx` liest jetzt `max-w-[var(--sheet-width,24rem)]`, `ReviewDrawer` setzt 44rem
  (≈700 px). Verworfen: `!max-w-*` mit `!important`, verworfen: Radix-Content selbst bauen.
- **2026-08-30 · Ist | Soll bricht nach der Kartenbreite um, nicht nach der Fensterbreite.**
  Der Scrollbereich der Karte ist `@container`, die zwei Spalten erscheinen ab `@min-[38rem]`
  (≈19rem je Spalte, genug für einen ganzen Satz). `sm:` maß das Browserfenster und damit
  das Falsche – im Drawer sagt es nichts über den vorhandenen Platz. Container-Queries sind
  in Tailwind v4 im Kern, keine neue Abhängigkeit.
- **2026-08-30 · Drei Fälle rechts statt zwei: Soll / Empfehlung / kein Soll.** Freigabe
  Victor. `proposed.value` gesetzt → „Soll" mit Wert; nur `proposed.display` → „Empfehlung"
  mit dem Satz; weder noch → „Soll" mit „Kein Soll ermittelbar – Entscheidung/Prüfung".
  Grund: ein Handlungssatz ist ein Soll, nur keines, das in ein Feld passt; der feste
  Hinweis behauptete dort Ratlosigkeit, wo eine Empfehlung steht. F-9d0b3f6a1c7e (nur
  Optionen) behält den Hinweis wie in der Spec.
- **2026-08-30 · Überschrift der Evidenzkarte ist die Referenz, der Quellentyp steht klein
  darunter.** Freigabe Victor. „Regelprüfung" (`deterministic`) beschreibt die Hälfte aller
  Einträge und sagt nichts; `1000/2026/1900004411` sagt, worum es geht. Die Referenz steht
  wörtlich da – ein Wort wie „Beleg" davor stünde in keinem Feld; dafür liegt der Vorschlag
  `evidence.reference_kind` bei der Engine-Session.
- **2026-08-30 · Nach einer Entscheidung sind Übernehmen, Ablehnen und Zuweisen gesperrt.**
  Freigabe Victor. Ein zweiter Klick würde die erste Entscheidung stillschweigend
  überschreiben; der Weg zurück heißt „Zurücknehmen". Die Tastatur (`A`/`R`/`Z`) ist
  mitgesperrt, sonst umginge sie die Knöpfe. „Später" bleibt aktiv: es schreibt nichts,
  es springt nur zum nächsten offenen Finding.
- **2026-08-30 · „Findings-Datei laden" liegt im Datenstand-Banner.** Freigabe Victor.
  Die Datei wird nur im Speicher gehalten (kein `localStorage`), der Lauf-Kopf wird wie
  im Build-Skript abgeleitet. Unbrauchbare Dateien brechen mit Grund ab statt halb zu
  erscheinen (Regel 4); die Meldungen nennen nur Feldnamen, Regel-IDs und `finding_id`,
  nie Geschäftspartnerdaten (Regel 8).

- **2026-08-30 · Der Dubletten-Vergleich ersetzt Ist | Soll, statt ihn zu ergänzen.**
  Freigabe Victor. Bei `category: duplicate` steht in `current.value` kein Ist-Wert, sondern
  eine Liste von Konten; „Ist" und „Soll" nebeneinander beantworten die Frage nicht, die hier
  ansteht („wo unterscheiden sie sich"). `proposed.display` und `source_summary` bleiben als
  Kasten „Soll" unter der Tabelle stehen – sie gingen sonst verloren.
- **2026-08-30 · Aus Prosa werden keine Vergleichszeilen gelesen.** Freigabe Victor. Die
  Spec verlangt neun Felder je Konto; strukturiert vorhanden sind drei (aus `current.display`).
  Land, USt-ID, IBAN, Zahlungsbedingung, offene Posten und letzte Zahlung stecken als Fließtext
  in `proposed.display` und in Evidenz-Notizen – und dort jeweils nur für **ein** Konto.
  „45.210 € OP" in eine Zeile „Offene Posten" zu übernehmen hieße, dem einen Konto einen Betrag
  zuzuschreiben und dem anderen keinen: geraten, nicht gelesen. Die sechs Felder werden unter
  der Tabelle als Platzhalter benannt (Regel 4: nichts stumm verwerfen), nicht als leere Zeilen
  gezeigt – sechs Zeilen mit „–" sähen nach einer Lücke im Mandanten aus, es ist eine im Schema.
- **2026-08-30 · Konten werden über den normalisierten Schlüssel zugeordnet, nicht über die
  Position.** `entity.bp_key` trägt das Rollenpräfix (`C:0000100234`), `current.value` und
  `proposed.value` tragen es nicht. `normalizeAccount` streift Präfix und führende Nullen ab
  (nur zum Vergleich – angezeigt wird der Schlüssel unverändert, Regel 2). Dass das erste
  Segment zum ersten Konto gehört, steht nirgends; lässt sich die Zuordnung nicht belegen,
  gibt `buildDuplicateComparison` `null` zurück und die Karte zeigt den gewohnten
  Ist|Soll-Abschnitt. Eine halbe Tabelle wäre schlechter als gar keine.
- **2026-08-30 · Match-Chips kommen aus `evidence.value`, nicht aus der `note`.** Die Evidenz
  mit `source_type: model` trägt in `value` die Gründe in Listenform
  („name_norm gleich, street_norm gleich, postal_code gleich" → drei Chips, so die Abnahme);
  die `note` ist ein Satz über die Normalisierung und steht darunter.
- **2026-08-30 · Die Adresszeile wird nur zerlegt, wenn sie sich bei *allen* Konten in genau
  drei Teile teilt.** Sonst steht der Text als eine Zeile „Angabe" wörtlich da. Gemischt wird
  nicht – sonst stünde in einer Spalte ein Name, wo in der anderen die ganze Anschrift steht.
  `missingFields` folgt daraus, statt fest zu stehen: alles aus der Feldliste der Spec, wozu
  keine Zeile entstanden ist.

## Offene Fragen an die Engine-Session (`main`)

- **`entity.records` fehlt – der Dubletten-Vergleich hat nur ein Drittel seiner Zeilen.**
  *(2026-08-30, aus Aufgabe 4. Von der Spec als Pflicht-Rückmeldung genannt.)* Die Spec
  verlangt je Konto Name, Straße, PLZ/Ort, Land, USt-ID, IBAN, Zahlungsbedingung, offene
  Posten und letzte Zahlung. Das Finding liefert davon drei, und die nur als Fließtext:
  `current.value` = `"0000100234 | 0000100987"`, `current.display` = zwei an ` | ` gereihte
  Anschriften. Alles Weitere steht in Prosa (`proposed.display`: „45.210 € OP, letzte Zahlung
  12.08.2026") und dort jeweils nur für ein Konto – nicht vergleichbar. Vorschlag:

  ```yaml
  entity:
    records:                      # ein Eintrag je Konto des Clusters
      - bp_key: "<C:KUNNR>"
        fields:
          name1: <string|null>
          street: <string|null>
          postal_code: <string|null>
          city: <string|null>
          country: <string|null>          # ISO-2, wie LAND1
          vat_id: <string|null>
          iban_masked: <string|null>      # nur maskiert (Regel 8)
          payment_terms: <string|null>    # Schlüssel wie ZTERM
          open_items_eur: <string|null>   # zwei Dezimalen als String (Regel 2)
          last_activity_on: <YYYY-MM-DD|null>
  ```

  Alle Felder optional und nullbar, Beträge als String mit zwei Dezimalen (Regel 2), IBAN
  nur maskiert (Regel 8). Das UI zeigt heute die drei ableitbaren Zeilen und benennt die
  sechs fehlenden ausdrücklich als Platzhalter; mit `entity.records` fällt die Textzerlegung
  ersatzlos weg. Kein Blocker, aber die Abnahme der Aufgabe 4 („Feld-für-Feld-Vergleich",
  `docs/CONCEPT.md` Abschnitt 9) ist ohne das Feld nicht vollständig erreichbar.
- **Bei Dubletten fehlt der Golden Record je Feld.** *(2026-08-30, aus Aufgabe 4.)*
  `proposed.value` nennt das führende Konto (`0000100234`) – das reicht für die Krone über der
  Spalte. Das Glossar beschreibt den Golden Record aber als „führendes Konto **und je Feld den
  besten Wert**"; welcher Wert je Feld gewinnt, steht nur im Fließtext der `remediation.steps`
  („USt-ID von 0000100987 … auf 0000100234 übernehmen"). Vorschlag: in `entity.records` oder
  neben `proposed.value` je Feld die Herkunft des Zielwerts angeben (z. B.
  `golden_record: {vat_id: "C:0000100987", name1: "C:0000100234"}`). Dann kann die
  Vergleichstabelle den Zielwert markieren, statt ihn dem Leser zu überlassen. Kein Blocker.
- **`title` ist im Schema optional, die Liste braucht es aber.** *(2026-08-30 an die
  Engine-Session übergeben, Antwort offen.)* Die Findings-Tabelle hat
  eine Spalte Titel; fehlt er, steht dort „—". Vorschlag: `title` zur Pflicht machen
  (max. 120 Zeichen wie bisher beschrieben). Kein Blocker.
- **Für „Zuweisen" gibt es im Schema kein Feld.** `decision` kennt nur `by`, `at`,
  `reason`, `reason_code`; `by` ist der Entscheider, nicht der Empfänger. Das UI führt
  den Empfänger als `assigned_to` im eigenen Entscheidungssatz und exportiert ihn in
  Aufgabe 7 als zusätzliches Feld. Vorschlag: `decision.assigned_to` (optional, String)
  ins Schema aufnehmen. Kein Blocker.
- **`proposed.display` von F-e2f7b19c4d83 beginnt mit „Kein Soll ermittelbar".** Die
  Dopplung auf der Karte ist mit Aufgabe 3b weg (der feste Hinweis erscheint dort nicht
  mehr), der Vorschlag ans Schema bleibt: Über der Spalte steht jetzt „Empfehlung", darunter
  liest sich „Kein Soll ermittelbar – keine zweite Quelle. Anfrage an Lieferant …" wie ein
  Widerspruch. Vorschlag: `proposed.display` mit der Handlung beginnen („Anfrage an
  Lieferant über bekannte Telefonnummer …"); die fehlende zweite Quelle steht schon in
  `source_summary`. Kein Blocker.
- **`evidence.reference_kind` fehlt.** *(Vorschlag Victor, 2026-08-30.)* Die Evidenzkarte
  trägt seit 3b die Referenz als Überschrift. Was die Referenz ist, steht aber nirgends:
  `1000/2026/1900004411` ist ein Beleg, `KNA1.LAND1` ein Stammfeld, `cluster-000412` ein
  Cluster – `source_type` unterscheidet das nicht (alle drei Beispiele stehen unter
  `deterministic` bzw. `model`). Vorschlag: `evidence.reference_kind` (optional, Enum)
  mit `document | master_field | cluster | external_query | statement`; das UI stellt der
  Referenz dann das passende Wort voran („Beleg 1000/2026/1900004411"). Bis dahin steht
  die Referenz wörtlich da, ohne erfundenes Substantiv. Kein Blocker.
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
- **2026-08-30 · Aufgabe 3 (Review-Karte).** Karte in acht Abschnitten in Spec-Reihenfolge
  (`src/components/review/`), leere Abschnitte erscheinen gar nicht. Entscheidungen mit
  Pflichtgrund beim Ablehnen, Empfänger beim Zuweisen, Sprung zum nächsten offenen Finding,
  Tastatur `A`/`R`/`Z` und `J`/`K` in der offenen Karte. Schadensklasse 1 sperrt
  „Übernehmen". 154 Tests grün (neu: `review`, `decisions`, `ReviewCard.render`),
  `npm run lint` und `npm run build` ohne Befund.
  Nächster Schritt: Aufgabe 4 – Dubletten-Vergleich für F-7b2e8c1d9a3f.
- **2026-08-30 · Erster Durchlauf durch die sechs Findings (Victor).** Fünf Beobachtungen,
  die als Aufgabe 3b vor Aufgabe 4 abgearbeitet werden:
  1. **Der Drawer ist zu schmal.** Ist und Soll quetschen sich, die Quellenlage wird zur
     Textwand. Er braucht etwa die doppelte Breite (~700 px); Ist | Soll stehen nur dann
     nebeneinander, wenn jede Spalte ein ganzer Satz sein darf.
  2. **„Kein Soll ermittelbar" ist falsch, wenn `proposed.value` leer, aber
     `proposed.display` vorhanden ist.** Dann lautet die Überschrift „Empfehlung"; der
     Hinweis „Kein Soll ermittelbar" gilt nur bei komplett fehlendem `proposed`.
  3. **Das Evidenz-Label „Regelprüfung" sagt nichts.** Überschrift der Evidenzkarte ist die
     Referenz (z. B. „Beleg 1000/2026/1900004411"), der Quellentyp steht klein darunter.
  4. **Nach einer Entscheidung bleiben Übernehmen/Ablehnen/Zuweisen aktiv.** Einmal
     entschieden, werden sie deaktiviert; nur „Zurücknehmen" bleibt.
  5. **„v1.0" steht allein in einer Zeile im Kopf.** Die Version gehört hinter die Regel-ID.
- **2026-08-30 · Aufgabe 3b (Nacharbeit Review-Karte).** Fünf Punkte umgesetzt: Drawer
  44rem statt faktisch 24rem (die alte Breitenklasse war wirkungslos, siehe Entscheidung),
  Ist | Soll über `@container` statt `sm:`, „Empfehlung" als dritter Fall neben Soll und
  „Kein Soll ermittelbar", Referenz als Überschrift der Evidenzkarte, Sperre der drei
  Entscheidungen nach der Entscheidung (auch für `A`/`R`/`Z`), Regel-ID und Version in
  einer Zeile. 158 Tests grün (vier neue in `ReviewCard.render`), `npm run lint` und
  `npm run build` ohne Befund. Neue Schema-Rückmeldung: `evidence.reference_kind`.
  Nächster Schritt: Aufgabe 4 – Dubletten-Vergleich für F-7b2e8c1d9a3f.
- **2026-08-30 · Aufgabe 4 (Dubletten-Vergleich).** `src/lib/duplicate.ts` (reine Logik:
  Kontenzuordnung über normalisierte Schlüssel, Zeilen aus `current.display`, Match-Chips,
  führendes Konto, Diff je Zeile) und `src/components/review/DuplicateCompare.tsx`; die
  Review-Karte schaltet bei `category: duplicate` darauf um und fällt auf Ist|Soll zurück,
  wenn die Daten den Vergleich nicht tragen. F-7b2e8c1d9a3f zeigt zwei Spalten, hervorgehobene
  Unterschiede (Müller/Mueller, Str./Straße), gleiche PLZ/Ort zurückgenommen, drei Match-Chips
  und die Krone auf `C:0000100234`. 182 Tests grün (neu: `duplicate`, fünf neue in
  `ReviewCard.render`), `npm run lint` und `npm run build` ohne Befund. Zwei neue
  Schema-Rückmeldungen: `entity.records`, Golden Record je Feld.
  Nächster Schritt: Aufgabe 5 – Belegpaar-Ansicht für F-003 (Doppelzahlung).
