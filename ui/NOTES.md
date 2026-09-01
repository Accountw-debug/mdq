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

- **2026-08-30 · Ab 30.08.: UI ist Produktcode, kein Prototyp.** Freigabe Victor. Daraus
  folgen drei Festlegungen: Datenzugriff hinter einem `FindingsSource`-Adapter (Datei,
  später Lauf-Verzeichnis oder API, ohne dass die Screens es merken); Export-/Import-Format
  für Entscheidungen als spätere Persistenz festziehen (was Aufgabe 7 schreibt, muss sich
  auch wieder einlesen lassen); Tabelle virtualisierungsfähig schneiden (Zeilenhöhe und
  Zeilenzugriff so, dass ein Fenster über 10.000 Findings ohne Umbau nachrüstbar ist).
  Grund: der Satz „das Design bleibt, der Code ist austauschbar" aus der Spec gilt nicht
  mehr – was hier entsteht, wird weitergepflegt. Verworfen: Prototypen-Freiheiten jetzt
  und Aufräumen später.

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

- **2026-08-30 · Die Belegpaar-Ansicht steht vor Ist|Soll und ersetzt es nicht.** Freigabe
  Victor. Anders als bei der Dublette steht in `current` ein echtes Feld (`BSAK.XBLNR`), und
  der fehlende Bindestrich zwischen „RE-4711" und „RE4711" ist der Kern des Findings – Ist|Soll
  bleibt also stehen. Die erste Frage am Schreibtisch lautet aber „welche zwei Belege", nicht
  „welches Feld"; deshalb steht die Belegansicht darüber. Verworfen: Belegpaar zwischen Ist|Soll
  und Evidenz, verworfen: Belegpaar an Stelle von Ist|Soll wie bei der Dublette.
- **2026-08-30 · Beleg und Evidenz werden über die Referenz verbunden, nicht über die Position.**
  `entity.documents` trägt nur den Schlüssel; Referenz, Datum und Betrag stehen im Text der
  Evidenz, deren `reference` `"<BUKRS>/<GJAHR>/<BELNR>"` lautet. Die Zuordnung ist damit belegt
  (anders als bei der Dublette, wo sie geraten gewesen wäre). Zweiter Versuch: die Belegnummer
  als **ganzes** Segment der Referenz – als Teilzeichenkette fände `1900004411` auch
  `11900004411`. Findet ein Beleg keine Evidenz, gibt `buildDocumentPair` `null` zurück und die
  Karte sieht aus wie jede andere; zwei halbe Belegkarten sind schlechter als keine.
- **2026-08-30 · Der Evidenztext wird zerlegt, aber alles oder nichts.** Aus „RE-4711, Belegdatum
  01.03.2026, bezahlt 28.03.2026" werden drei Felder – nur dann, wenn das Muster bei **jedem**
  Beleg greift; sonst steht bei allen der Satz wörtlich da. Dieselbe Regel wie beim Adress-Split
  in Aufgabe 4: sonst stünde auf einer Karte ein Feldraster und auf der anderen ein Satz. Der
  Widerspruch zu „aus Prosa werden keine Vergleichszeilen gelesen" ist keiner – dort war die
  Zuordnung zum Konto ungeklärt, hier nennt die Referenz den Beleg.
- **2026-08-30 · Der Betrag je Beleg wird benannt, nicht zugeschrieben.** Freigabe Victor.
  32.000,00 € ist die Euro-Wirkung des Findings und steht als Prosa in `current.display`
  („Zwei bezahlte Rechnungen über 32.000,00 EUR"); dass **jeder einzelne** Beleg über diesen
  Betrag lautet, steht in keinem Feld. Unter den Karten steht deshalb ein Satz „Platzhalter:
  Betrag je Beleg …" (Regel 4). Die Abnahme „F-003 vollständig" ist damit bis zur
  Schema-Erweiterung formal knapp verfehlt.
- **2026-08-30 · Die Quellenlage steht bei der Belegansicht nur einmal.** `source_summary` ist
  der Fuzzy-Grund und gehört unter die Karten („Warum dieses Paar"); `CurrentProposed` bekommt
  dafür die Prop `omitSourceSummary`. Verworfen: denselben Satz zweimal auf derselben Karte
  stehen lassen – zwei Vorkommen lesen sich wie zwei Aussagen.
- **2026-08-30 · Das Evidenz-Panel bleibt vollständig.** Die Belegansicht verbraucht keine
  Einträge, sie liest sie nur mit; „Evidenz (3)" zeigt weiterhin alle drei. Die Belegkarte ist
  die Lesehilfe, das Panel die Liste, gegen die geprüft wird. Verworfen: Einträge oben
  „aufbrauchen" – dann verschwände das Panel bei F-c41d7e9b2a60 ganz und mit ihm die Zusage aus
  Aufgabe 3, dass dort jede Quelle steht.
- **2026-08-30 · `line_item` im Typ optional.** Das Schema führt es nicht unter `required`
  (`entity.documents[].required = [company_code, fiscal_year, document_no]`), der Typ verlangte
  es. Jetzt `line_item?: string | null` – der Vertrag ist das Schema, nicht die Beispieldatei.

- **2026-08-30 · Der Datenzugriff liegt hinter `FindingsSource` (`src/sources/`).** Aufgabe 5b,
  Punkt 1. `src/lib/load-run.ts` ist aufgelöst in `sources/findings-source.ts` (Vertrag),
  `sources/parse.ts` (Prüfen und Ableiten, rein), `sources/{build,file}-source.ts` und
  `sources/index.ts`. Der naheliegende Name `src/data/` geht **nicht**: die Wurzel-`.gitignore`
  ignoriert `data/` auf jeder Ebene („Daten – niemals einchecken"), die Dateien wären
  unbemerkt nicht im Commit gelandet. Ein `!`-Ausnahme in `ui/.gitignore` wäre ein Loch in
  genau der Regel, die verhindert, dass Daten eingecheckt werden – dafür ist der Ordnername
  zu wenig wert.
  Zum Vertrag gehört mehr als die Signatur: jede Implementierung führt ihre Daten durch
  `parse.ts` (dieselben Prüfungen für Datei und später API), Fehler verlassen eine Quelle
  **immer** als `LoadError` mit deutscher Meldung (Regel 4), Meldungen nennen nur Feldnamen,
  Regel-IDs und `finding_id` (Regel 8). `DEFAULT_SOURCE` in `sources/index.ts` ist die einzige
  Stelle, die ein Backend austauscht. Verworfen: eine Lauf-Auswahl (`listRuns`) in derselben
  Schnittstelle – das ist ein eigener Vertrag und ein eigenes Feature (siehe offene Punkte).
- **2026-08-30 · Der Quellenwechsel läuft über Zustand, nicht über einen zweiten Aufruf.**
  `App` hält `source` (was gelten soll) und `loaded` (was zu sehen ist, **mitsamt der Quelle,
  aus der es stammt**). Sonst stünde nach einer unbrauchbaren Datei ihr Name im Banner über
  den alten Daten. Der Ladeeffekt hängt allein an `source` und bricht mit `AbortController`
  ab, damit ein schneller Wechsel nicht das alte Ergebnis nachschiebt.
- **2026-08-30 · `decisions.json` ist ein versionierter Umschlag, kein nacktes Array.**
  Aufgabe 5b, Punkt 2. `{format: "mdq.decisions", format_version: 1, run_id, data_as_of,
  engine_version, pack_version, exported_at, exported_by, decisions: [...]}`; Vertrag in
  `src/types/decisions-file.ts`, Umsetzung in `src/lib/decisions-io.ts`. Versionsregel:
  zusätzliche optionale Felder lassen die Version stehen (ein älterer Leser nennt sie als
  unbekannt, Regel 4), alles was einen älteren Leser falsch verstehen ließe erhöht sie; ein
  Leser nimmt genau die Versionen, die er kennt. `sample_reviewed` (Aufgabe 7) ist im Vertrag
  benannt und heute **nicht** geschrieben. Die Sätze stehen nach `finding_id` sortiert –
  gleicher Stand, gleiche Datei bis aufs Byte (Regel 9). Verworfen: das Array aus der Spec
  ohne Umschlag – ohne Lauf-Kopf ist beim Einlesen nicht prüfbar, wozu die Datei gehört.
- **2026-08-30 · Der Import ersetzt den Stand der Sitzung, mit Rückfrage.** Freigabe Victor.
  „Gestern weitergearbeitet" ist ein Zustand, nicht die Summe zweier. Liegen lokale
  Entscheidungen vor, fragt `ImportDecisionsDialog` vorher – mit dem Bericht **vor** der
  Übernahme und dem Hinweis, erst zu sichern. Zusammenführen zweier Stände ist als späterer
  Punkt notiert, nicht gebaut.
- **2026-08-30 · Ein anderer `run_id` in der Entscheidungsdatei ist eine Warnung, kein
  Abbruch.** Freigabe Victor. `finding_id` ist deterministisch (Regel 9), ein Finding kann im
  nächsten Lauf denselben Schlüssel tragen. Angewandt wird nur, was ein Finding im geladenen
  Lauf findet; der Bericht sagt immer zuerst, wie viele das sind und wie viele nicht, und
  nennt die übrigen `finding_id`s einzeln (Regel 4). Abgebrochen wird nur, wenn die Datei als
  Ganzes nicht taugt: falsches `format`, unbekannte `format_version`, kaputter Satz.
- **2026-08-30 · `exported_by` füllt den Bearbeiter nur, wenn dort nichts steht.** Der Fall
  „derselbe Bearbeiter, nächster Tag" spart sich damit das Tippen; ein bereits eingetragener
  Name wird nie stillschweigend überschrieben.
- **2026-08-30 · Der Berichtstext ist eine reine Funktion** (`describeImport`), nicht Text in
  der Komponente. Grund: der Wortlaut steht damit im Test, und Dialog und Banner sagen
  dasselbe.
- **2026-08-30 · Die Tabelle ist virtualisierungsfähig geschnitten – ohne Virtualisierung.**
  Aufgabe 5b, Punkt 3. Fünf Dinge: (1) Der Zeilentyp `FindingRow` trägt die Entscheidung
  **in den Daten**, nicht in einer Closure der Spaltendefinition – vorher baute jede
  Entscheidung alle Spalten und damit die ganze Tabelle neu; `COLUMNS` ist jetzt konstant.
  `finding.decision` reicht dafür nicht, dort steht schemakonform keine `action`.
  (2) `ROW_HEIGHT = 56` als Konstante: jede Zeile genau zwei Textzeilen hoch, die spätere
  `estimateSize`. (3) Eigener begrenzter Scrollbereich mit klebendem Kopf statt einer
  scrollenden Seite. (4) Zeilenzugriff über `scrollToIndex(index)` und `indexOfId` statt
  `querySelector('[data-selected]')` – mit Virtualisierung ist die gewählte Zeile womöglich
  gar nicht gerendert. (5) `FindingsTableRow` mit `memo`; das greift, weil TanStack das
  Zeilenmodell an `table.options.data` bindet (`createCoreRowModel`, `memoDeps`) und die
  Zeilenobjekte damit stabil bleiben, solange die sichtbare Liste dieselbe ist. Ein Fenster
  über 10.000 Findings ersetzt danach nur die Schleife in `FindingsTable`.
- **2026-08-30 · Kein `@tanstack/react-virtual` installiert.** Der Nachrüstpunkt steht, die
  Abhängigkeit nicht – sie bräuchte einen eigenen Eintrag hier, und die sechs Beispiele
  brauchen sie nicht. Sechs Zeilen zu virtualisieren wäre Aufwand ohne Wirkung.
- **2026-08-30 · `src/components/ui/table.tsx` nimmt `containerClassName` und `containerRef`.**
  Zweite Anpassung an einer shadcn-Primitive nach `sheet.tsx`. Der Container ist der
  scrollende Vorfahr, an dem `position: sticky` und später der Virtualizer hängen; ohne die
  beiden Props ließe er sich von außen weder begrenzen noch messen. Verworfen: einen eigenen
  Scroll-Wrapper darum legen – dann gäbe es zwei ineinander liegende Scrollbereiche, und
  `sticky` klebte am falschen.
- **2026-08-30 · Der App-Rahmen ist fensterhoch und scrollt nicht.** `AppShell` ist `h-svh`
  mit `overflow-hidden`, der Inhalt eine Flex-Spalte mit `min-h-0`; der Explorer füllt sie und
  seine Tabelle scrollt in sich. **Folge für Aufgabe 6:** eine Ansicht, die selbst lang wird
  (Dashboard), bringt ihr eigenes `overflow-y-auto` mit. Das ist die einzige sichtbare
  Änderung der Aufgabe 5b; Freigabe Victor.

- **2026-08-30 · Die Euro-Wirkung wird je Währung summiert, nie umgerechnet.** Freigabe
  Victor. Aufgabe 6. `summarize` gibt `totals: MoneyTotal[]` zurück, nicht einen Betrag;
  mit den sechs Beispielen ist das genau eine Zeile („73.042,40 €"). Ein Kurs stünde in
  keinem Feld des Findings, und eine Summe ohne Währung ist keine Zahl (CLAUDE.md, Regel 2).
  Verworfen: über `impact_eur.amount` hinwegsummieren und die Währung der ersten Zeile
  drüberschreiben.
- **2026-08-30 · Die Top-Liste enthält nur Findings mit `impact_eur`.** Freigabe Victor.
  `impactCents` zählt ein fehlendes `impact_eur` als 0 – in einer Rangliste „nach
  Euro-Wirkung" stünde damit ein Finding mit „0,00 €", dem keine Regel einen Betrag
  zugeschrieben hat. Die übrigen werden unter der Liste gezählt („2 Findings ohne
  Euro-Wirkung"), statt still zu verschwinden (Regel 4). Dieselbe Regel in der
  Kategorie-Kachel: eine Kategorie ohne Betrag bekommt „keine Euro-Wirkung", keine Null.
- **2026-08-30 · Der Sprung aus dem Dashboard ist ein Reducer-Schritt (`focus_finding`).**
  Freigabe Victor. Tab, Filter, Suche, Auswahl und Drawer in einer Aktion: sonst gehörte die
  offene Karte zu einer Zeile, die die Liste dahinter gerade wegfiltert – `J` liefe ins Leere
  und die Auswahl verschwände beim nächsten Filterwechsel. War eine Filterung eingestellt,
  trägt der Zustand `filtersResetNotice` und der Explorer zeigt eine dezente Zeile „Filter
  zurückgesetzt" (Zusatz Victor); sie räumt sich nach 6 Sekunden selbst weg und bei jeder
  Änderung an Tab, Filter oder Suche ohnehin. Verworfen: ein zweiter `ReviewDrawer` im
  Dashboard – dort gäbe es keine Liste, durch die `J`/`K` laufen könnten.
- **2026-08-30 · Das Dashboard rechnet über den ganzen Lauf, die Entscheidungen der Sitzung
  zählen mit.** Freigabe Victor. Filter gehören zur Suche, nicht zur Lage – die Kacheln
  beschreiben den Datenstand und ändern sich nicht, wenn im Explorer ein Filter steht. Die
  Entscheidungen liegen dagegen schon als Überlagerung über den Findings (`applyDecisions`
  in `App`), also fällt „davon offen" sofort, auch ohne Export.
- **2026-08-30 · Die Score-Kachel nennt keine Zahl.** Sie steht mit gestricheltem Rand und
  dem Text „ab Sprint 4" da (so die Spec); der Rauchtest prüft ausdrücklich, dass in ihrem
  Abschnitt kein Zahlenknoten steht. Grund: der Score ist die eine Kennzahl auf diesem
  Bildschirm, die niemand nachrechnen kann – ein Platzhalterwert würde geglaubt.
- **2026-08-30 · Der Anteil je Stufe steht als Bruch („3 von 6"), nicht als Prozentzahl.**
  Bei sechs Findings ist „50 %" eine gerundete Behauptung über drei Stück. Alle vier
  Stufen stehen da, auch die leere: dass es keine Stufe A gibt, ist die Aussage.
  **Nachtrag (Aufgabe 7, Freigabe Victor):** Der Balken daneben ist gestrichen. Bei vier
  Zeilen mit zweistelligen Zahlen trug er nichts, was der Bruch nicht schon sagt, und ein
  gerundetes Bild neben einer exakten Zahl lädt zum Ablesen des Bildes ein.
- **2026-08-30 · Kategorien werden Währung für Währung verglichen, in der Reihenfolge des
  Laufs.** Bei einer Währung ist das schlicht „nach Betrag absteigend"; bei mehreren bleibt
  es eine feste Reihenfolge, ohne einen Kurs zu erfinden. Gleichstand geht nach
  Kategoriename, damit nichts der Einfügereihenfolge einer `Map` überlassen bleibt (Regel 9).
- **2026-08-30 · Die Stichproben-Freigabe setzt `in_progress`, nicht `done`.** Freigabe
  Victor; die Spec-Stelle in `docs/specs/SPRINT-5-UI.md` (Aufgabe 7: „alle Findings der
  Gruppe auf `done`") gilt damit als überholt und ist beim Merge dort zu korrigieren.
  Grund: `done` hieße „in SAP umgesetzt", und das weiß das UI nicht – es weiß nur, dass
  entschieden wurde. `done` vergibt der nächste Lauf, in dem das Finding nicht mehr
  auftaucht (dieselbe Regel wie bei der Einzelentscheidung seit Aufgabe 3). Verworfen:
  eine vierte Aktion `release` mit eigenem Status – zwei Wege zu „übernommen" wären eine
  Unterscheidung ohne Unterschied.
- **2026-08-30 · Eine Ablehnung in der Stichprobe sperrt die Gruppenfreigabe für diesen
  Lauf endgültig.** Freigabe Victor. Wenn die Regel schon an einem von zehn geprüften
  Fällen falsch liegt, ist die Grundlage für „die anderen 230 stimmen auch" weg. Die
  übrigen Findings bleiben einzeln entscheidbar, und die Sperre sagt das ausdrücklich –
  sie nimmt Arbeit weg, keine Möglichkeiten. Der Ausgang steht in `decisions.json`
  (`sample_reviewed`), sonst wäre „endgültig" nur bis zum Feierabend wahr. Verworfen:
  eine neue Stichprobe nach einer Ablehnung ziehen zu lassen – das ist Würfeln, bis es
  passt.
- **2026-08-30 · Die Stichprobe wird aus den offenen, freigebbaren Findings der Gruppe
  gezogen, mit Seed aus `run_id` und `rule_id`.** Gleicher Lauf und gleiche offene Menge
  ergeben dieselbe Auswahl (Regel 9, kein `Math.random`); gemischt wird über die nach
  `finding_id` sortierte Liste, damit die Sortierung der Tabelle die Auswahl nicht
  verschiebt. Schadensklasse 1 ist weder Kandidat noch Ziel einer Freigabe (Regel 11) und
  wird an der Gruppe genannt, nicht verschwiegen. Verworfen: aus allen Findings der Gruppe
  zu ziehen – dann stünden schon entschiedene Fälle in der Stichprobe und eine alte
  Ablehnung sperrte die Gruppe, ohne dass jemand etwas getan hat.
- **2026-08-30 · Die Bereinigungsliste enthält nur die übernommenen Massenänderungen.**
  Sie ist eine Arbeitsanweisung fürs SAP-Team, keine Bestandsaufnahme des Laufs; wer
  nichts entschieden hat, bekommt keine Zeile. Freigabe Victor. Format: Trenner `;`,
  CRLF, UTF-8 **mit** BOM (ohne BOM zerlegt Excel die Umlaute), Felder mit `;` oder `"`
  nach RFC 4180 gequotet, Reihenfolge Regel → Geschäftspartner → `finding_id`. In den
  Spalten stehen Schlüssel und Feldwerte, keine Namen oder Adressen. Verworfen: TSV
  (unsichtbarer Trenner) und CSV ohne BOM (Umlaute kaputt beim Doppelklick).
- **2026-08-30 · Stichproben liegen in einem eigenen Reducer neben den Entscheidungen.**
  `state/samples.ts` statt einer erweiterten `DecisionsState`. Grund: eine Freigabe
  *schreibt* Entscheidungen, ist aber selbst keine – und die Sperre nach einer Ablehnung
  ließe sich aus den Entscheidungen gar nicht ablesen, weil sie keine erzeugt. Verworfen:
  beides in einen zusammengesetzten Zustand zu ziehen; das hätte jede Stelle angefasst,
  die heute mit `Record<finding_id, DecisionRecord>` arbeitet.
- **2026-08-31 · `src/types/finding.ts` steht auf Schema 1.1; Quelle ist die Schemadatei.**
  Nachgezogen wurden alle Felder aus D-069: `evidence[].reference_kind` (Enum aus acht
  Werten, jetzt als `REFERENCE_KINDS` mit im Driftschutz), die Beleg-Erweiterungen
  `reference`/`document_date`/`cleared_on`/`amount`/`currency`, `entity.records[]`
  (`{bp_key, fields}`), `proposed.golden_record` und `decision.assigned_to` – alle
  optional wie im Schema. `GoldenRecord` ist als `{ [F in keyof RecordFields]?:
  GoldenRecordEntry }` geschrieben statt als zweite Feldliste: die beiden Listen dürfen
  nicht auseinanderlaufen (D-069, Punkt 6), und ein Mapped Type macht daraus eine
  Zusage des Compilers statt eine Absprache. Verworfen: die elf Felder ein zweites Mal
  aufzuzählen.
- **2026-08-31 · `relevance` heißt `open_items`/`volume_12m` + `currency`, und die Karte
  zeigt die Währung aus dem Finding.** Die alten Namen `open_items_eur`/`volume_12m_eur`
  sind weg (D-069, Punkt 5: der Währungsname steckt seit D-030 nicht mehr im Feldnamen).
  `Relevance.tsx` formatiert deshalb über `formatMoney(betrag, relevance.currency)` statt
  über `formatEur` – die Beträge stehen in der Hauswährung des Buchungskreises und sind
  nicht umgerechnet; ein festes Eurozeichen hätte bei einem Mandanten mit CHF-Buchungskreis
  einen falschen Betrag behauptet (Regel 2). `currency` allein lässt den Abschnitt weiter
  verschwinden: die Währung ist Pflicht, sobald der Block dasteht, und trägt für sich
  genommen keine Aussage.
- **2026-08-31 · `title` ist Pflicht – auch an der Ladegrenze, nicht nur im Typ.**
  Das Schema führt `title` unter `required` (D-069, Punkt 5); `finding.ts` sagt jetzt
  `title: string` statt `title?: string`. Damit der Typ nicht über die Daten lügt, prüft
  `checkFinding` in `@/sources/parse` das Feld mit, und die drei Notbehelfe im UI
  (`title ?? '—'`, `title ?? rule_id`, `title ?? ''`) sind ersatzlos weg. Grund: eine
  Datei ohne `title` ist gegen Schema 1.1 ungültig, und eine leere Zelle wäre genau das
  stille Verschlucken, das Regel 4 verbietet. Verworfen: den Typ optional zu lassen und
  die Fallbacks stehenzulassen – dann bleibt offen, ob eine leere Titelspalte ein Daten-
  oder ein Anzeigefehler ist.
- **2026-08-31 · Der Lauf-Kopf kommt aus `run.json`, nicht aus den Findings.** Bis Sprint 3
  gab es nur `findings.json`, und `deriveRun` hat den Kopf daraus abgeleitet. Seit
  `mdq run` liegt `runs/<run_id>/run.json` daneben und ist die Quelle: `tables_loaded` ist
  dort echt, und `company_codes` nennt die Buchungskreise **des Laufs** – einschließlich
  derer ohne Befund, die aus den Findings gar nicht ableitbar sind. „Findings-Datei laden"
  nimmt deshalb jetzt mehrere Dateien entgegen; unterschieden werden sie am Inhalt
  (Liste bzw. `{findings: […]}` gegen Objekt mit `run_id`), nicht am Dateinamen, damit
  ein umbenannter Export trotzdem richtig landet. `deriveRun` bleibt als Notbehelf für
  „nur `findings.json` zur Hand", dann weiterhin mit `tables_loaded: 0`. Passt die `run_id`
  der beiden Dateien nicht zusammen, ist das ein Fehler mit Meldung, keine Mischung
  (Regel 4). Verworfen: die Dateien am Namen zu erkennen; verworfen auch, `run.json` zur
  Pflicht zu machen – eine einzelne Findings-Datei bleibt ansehbar.
- **2026-08-31 · `scripts/build-data.mjs` ist ausdrücklich der Ersatz für die sechs
  Beispiel-Findings, kein Lauf.** `tables_loaded: 0` steht dort jetzt kommentiert für
  „hier lief keine Engine, es wurde keine Tabelle geladen"; das Banner blendet die Angabe
  bei 0 aus, statt eine Zahl zu erfinden. Ebenso sind die `company_codes` dort eine
  Ableitung aus sechs Beispielen und kein Laufumfang. Das Skript bleibt, weil die
  Gestaltung und die Tests auch ohne Engine-Lauf etwas zum Anzeigen brauchen.
- **2026-08-31 · Der Driftschutz löst `$ref` auf.** Schema 1.1 hat die Wiederholungen
  nach `$defs` gezogen (D-069, Punkt 7); der Enum-Test lief danach in „Pfad im Schema
  nicht gefunden" – ein Schema-Umbau, gemeldet als fehlendes Feld. `at()` folgt jetzt
  `{"$ref": "#/$defs/…"}` (mit Kreis-Erkennung), und dazugekommen sind drei Proben:
  `version` ist `"1.1"`, `title` steht unter `required`, und `entity.records[].fields`
  und `proposed.golden_record` führen dieselben Feldnamen. Verworfen: die Enum-Liste im
  Test wörtlich zu wiederholen – dann prüft der Test sich selbst.
- **2026-08-31 · Spec-Korrektur: die Gruppenfreigabe setzt `in_progress`, nicht `done`.**
  `docs/specs/SPRINT-5-UI.md`, Aufgabe 7 stand auf `done`; der Code setzt seit Aufgabe 7
  `in_progress`. Korrigiert wurde die Spec, nicht der Code: die Freigabe ist eine
  Entscheidung, keine Umsetzung – `done` gehört an die Rückmeldung aus SAP, nicht an den
  Klick im UI. Dieselbe Begründung trägt schon die Einzelentscheidung „Übernehmen".
- **2026-09-01 · `impact_eur` bekommt in Sprint 4 eine Art: `loss` oder `exposure`.**
  *(Entscheid Victor, aus der Schlusshandprobe.)* Die Top-10 nach Euro-Wirkung wird
  heute von einem AR-VAL-003-Finding angeführt (IBAN mit ungültiger Prüfziffer,
  **862.561,72 €**) und schiebt die tatsächlichen Doppelzahlungen auf Platz 6 und
  tiefer. Beide Zahlen stehen zu Recht in `impact_eur`, meinen aber Verschiedenes: bei
  der Doppelzahlung sind 32.000,00 € **abgeflossen**, bei der falschen IBAN sind
  862.561,72 € **gefährdet** – offene Posten, die über eine unbrauchbare Bankverbindung
  laufen sollen. Heute unterscheidet sie nur `impact_eur.formula`, also Freitext, den
  keine Rangliste lesen kann. In Sprint 4 bekommt `impact_eur` deshalb ein Feld für die
  Art (`loss` = eingetretener Abfluss, `exposure` = gefährdetes Volumen). Das UI
  summiert und sortiert danach getrennt und mischt die beiden nicht mehr in eine
  Rangliste. Verworfen: die Gewichtung im UI aus der Kategorie zu raten (`leakage` =
  Verlust, alles andere = Exposure) – das wäre eine Fachaussage, die kein Feld deckt;
  verworfen auch, das Feld einfach wegzulassen und weiter alles gemeinsam zu ranken,
  weil eine Rangliste, die einen Hinweis über einen Geldabfluss stellt, die Reihenfolge
  der Arbeit falsch vorgibt. Schemaänderung: Engine-Session, Sprint 4.

## Offene Fragen an die Engine-Session (`main`)

- **`proposed.display` von F-e2f7b19c4d83 beginnt mit „Kein Soll ermittelbar".** Die
  Dopplung auf der Karte ist mit Aufgabe 3b weg (der feste Hinweis erscheint dort nicht
  mehr), der Vorschlag ans Schema bleibt: Über der Spalte steht jetzt „Empfehlung", darunter
  liest sich „Kein Soll ermittelbar – keine zweite Quelle. Anfrage an Lieferant …" wie ein
  Widerspruch. Vorschlag: `proposed.display` mit der Handlung beginnen („Anfrage an
  Lieferant über bekannte Telefonnummer …"); die fehlende zweite Quelle steht schon in
  `source_summary`. Kein Blocker.
- **`entity.company_code` ist optional** – F-7b2e8c1d9a3f (Dublette) hat keinen. Das UI
  führt dafür den Filterwert „ohne Buchungskreis". Falls Dubletten-Findings künftig einen
  Buchungskreis bekommen sollen, sag Bescheid; erfunden wird hier keiner.
- **`entity.documents` bleibt bei AP-LEA-001 auf den Schlüsselfeldern stehen.**
  *(2026-09-01, aus der Schlusshandprobe am Lauf `2026-08-28-702323b8`.)* Die acht
  Doppelzahlungen tragen je zwei Belege, aber nur `company_code`/`fiscal_year`/
  `document_no`; `reference`, `document_date`, `cleared_on` und `amount` sind `null`.
  Die Belegkarten füllen sich deshalb weiter aus dem Evidenztext, der inzwischen nur
  noch die nackte Referenz enthält („RE-4711") – aus „RE-4711" lassen sich Belegdatum
  und Zahldatum nicht mehr zerlegen, also steht der Platzhalter „Referenz, Belegdatum,
  Betrag je Beleg steht nicht strukturiert im Finding" auf jeder dieser Karten.
  AR-LEA-001 füllt die Felder bereits vollständig, AP-LEA-001 also als einziges nicht.
  **Verabredet für Sprint 4 (AP-LEA-001 v1.1):** die vier Felder je Beleg füllen; das
  UI liest sie dann im Verdrahtungsdurchgang. Der Platzhaltersatz ist bis dahin
  außerdem schief formuliert – er sagt „kommt mit `entity.documents`", dabei ist das
  Feld längst da und nur nicht gefüllt; er wird im selben Durchgang umgeschrieben.

### Beantwortet

- **2026-08-30 · `created_at` immer UTC mit `Z`? – erledigt.** Ja: `created_at` kommt aus dem
  `RunContext` und ist immer UTC mit `Z` (D-028). Offsets wie `+02:00` treten nicht auf;
  `formatDateTime` darf sie weiter zurückweisen. Keine Änderung am Formatierer nötig.
- **2026-08-30 · `run.json` neben `findings.json`? – erledigt.** Ja: die Engine schreibt
  `runs/<run_id>/run.json` ab Sprint 3 neben `findings.json`. Das UI liest den Lauf-Kopf
  schon heute als eigene Datei (`RunInfo`), die echte Datei passt also ohne Codeänderung;
  `tables_loaded` ist dann echt statt `0`. `scripts/build-data.mjs` bleibt als Ersatz für
  den Prototyp, solange kein Lauf vorliegt.
- **2026-08-31 · Die vier Lücken aus den Aufgaben 4 und 5 – erledigt durch D-069.** Alle
  vier Rückmeldungen sind im Schema 1.1 angekommen, und in der vorgeschlagenen Form:
  `entity.documents[]` trägt `reference`, `document_date`, `cleared_on`, `amount` und
  `currency`; `evidence[].reference_kind` gibt es mit `netting` in der Enum-Liste, womit
  der Netting-Nachweis nicht länger am Wort „Netting" in einer `note` hängt;
  `entity.records[]` (`{bp_key, fields}`) macht den Feld-für-Feld-Vergleich möglich; und
  `proposed.golden_record` nennt je Feld den besten Wert mit Herkunft. Abweichungen von
  unserem Vorschlag, bewusst und in D-069 Punkt 5 begründet: `name` statt `name1`,
  `open_items` + `currency` statt `open_items_eur`. `src/types/finding.ts` steht auf
  diesen Namen. **Die Karte liest die Felder noch nicht** – das ist ein eigener
  Durchgang, siehe „Offene Punkte im UI".
- **2026-08-31 · `title` Pflicht und `decision.assigned_to` – erledigt durch D-069,
  Punkt 5.** `title` steht mit `minLength: 1`/`maxLength: 120` unter `required`,
  `decision.assigned_to` optional im Schema. Beides ist in `finding.ts` nachgezogen,
  `title` zusätzlich in der Ladeprüfung (`@/sources/parse`).
- **2026-08-31 · Der Lauf-Kopf liegt wirklich vor – über die Zusage hinaus eingelöst.**
  `runs/<run_id>/run.json` ist mit Sprint 3, Aufgabe 4 da und im UI angebunden. Die
  Handprobe am Lauf `2026-08-28-702323b8` zeigt „16 Tabellen" und die Buchungskreise des
  Laufs im Banner; `tables_loaded` ist damit echt statt 0.
- **2026-09-01 · Der unformatierte Betrag im Titel – erledigt.** Der Lauf vom 31.08.
  schreibt die Beträge im Titel deutsch („Mögliche Doppelzahlung: 42.100,00 EUR an
  Kreditor …"). Über alle 208 Findings und alle Freitextfelder – Titel, `display`,
  `source_summary`, Evidenzwerte und -notizen, Behebungsschritte – steht kein
  unformatierter Betrag und kein ISO-Datum mehr; umgekehrt bleiben die Datenfelder
  kanonisch (`-?\d+\.\d{2}` bzw. `JJJJ-MM-TT`), und im ganzen JSON steht kein einziger
  Float. Die Trennung „Freitext deutsch, Datenfelder ISO" trägt damit nachweislich.
- **2026-09-01 · `entity.display_name` – erledigt.** Im Lauf vom 31.08. ist das Feld in
  allen 208 Findings gefüllt („Hartmann Logistik e.K., Bremen"); die Spalte zeigt kein
  „—" mehr. Damit ist auch beantwortet, dass das Feld für den Betrieb gedacht ist. Regel 8
  bleibt davon unberührt: der Name steht im Finding und auf dem Bildschirm, nie in einem
  Log oder in einem Test.

## Offene Punkte im UI (keine Schema-Frage)

- **Verdrahtungsdurchgang: die Karte rechnet die neuen Felder noch aus Fließtext zurück.**
  *(2026-08-31 aufgenommen, 2026-09-01 nach der Schlusshandprobe präzisiert. Freigabe
  Victor: eigener Durchgang.)* Schema 1.1 liefert seit D-069 `entity.records`,
  `proposed.golden_record`, die Beleg-Erweiterungen und `evidence[].reference_kind`;
  `src/types/finding.ts` kennt sie, aber `src/lib/duplicate.ts`, `src/lib/documents.ts`
  und `EvidencePanel` lesen weiter `current.display`, `proposed.display` und die
  Evidenz-`note`. Der Lauf `2026-08-28-702323b8` füllt inzwischen `entity.records` (9
  Findings), `entity.documents` (14) und `evidence[].reference_kind` (160 Einträge,
  Werte `document`, `master_field`, `policy`, `statement`); `proposed.golden_record`
  bleibt in allen 208 leer. Damit ist der Durchgang nicht mehr theoretisch – er hat
  Daten. Sechs benannte Arbeiten – 1 bis 4 aus der Schlusshandprobe, 5 und 6 aus der
  Tab-1-Handprobe am selben Lauf; **5 und 6 sind am 2026-09-02 erledigt**, 1 bis 4
  gehören weiter dem Verdrahtungsdurchgang:
  1. **Der Dubletten-Vergleich muss `entity.records` lesen statt `current.value` zu
     zerlegen.** Heute verlangt `buildDuplicateComparison` ein Segment je Konto in
     `current.value` (`A | B`); CROSS-DUP-001 schreibt dort nur die USt-IdNr., also
     bricht der Aufbau ab und die Karte zeigt den gewohnten Ist|Soll-Block. Ergebnis:
     das zweite Konto (`related_bp_keys`, in `records` mit allen neun Feldern) steht
     nirgends auf der Karte, obwohl das Finding es mitliefert. Mit `records` entfällt
     das Zerlegen, und die sechs Platzhalterzeilen werden zu echten Zeilen.
  2. **Der Vergleich darf nicht länger an `category === 'duplicate'` hängen.**
     AP-CON-001 (dieselbe Bankverbindung bei zwei Kreditoren) liefert `records` für
     beide Konten, ist aber `consistency` und kommt deshalb nie an die Tabelle – während
     der eigene Behebungsschritt des Findings sagt „die Vergleichsfelder stehen im
     Finding". Künftige Bedingung: **`entity.records` vorhanden und mindestens zwei
     Einträge**, unabhängig von der Kategorie.
  3. **Die Belegkarte muss auch bei einem einzelnen Beleg erscheinen.** `buildDocumentPair`
     verlangt zwei Belege; AR-LEA-001 (Unapplied Cash) hat genau einen – vollständig
     gefüllt mit `document_date`, `amount` und `currency`. Der Beleg taucht deshalb nur
     als Referenz in der Evidenz auf. „Belegpaar" wird zu „Beleg(e)": eine Karte ab dem
     ersten Beleg, die Paar-Überschrift bleibt der Sonderfall bei zweien.
  4. **Die Ansicht „Regeln" wird aus `run.json` gefüllt.** `run.json` trägt unter `rules`
     je Regel `rule_id`, `status`, `findings` und `reason`; `run.json.totals` nennt
     `rules_executed`/`rules_skipped`/`rules_failed`. Damit ist die Verteilung je Regel
     ohne Regelkatalog anzeigbar – heute ist die Ansicht ein Platzhalter, und die
     Verteilung lässt sich nur zählen, indem man jede Regel-ID einzeln in die Suche
     tippt. Dafür braucht `RunInfo` das Feld `rules` (optional, wie alles aus `run.json`)
     und `checkRun` seine Prüfung. Eine übersprungene oder fehlgeschlagene Regel gehört
     mit ihrem `reason` sichtbar auf den Schirm – ein Lauf, der eine Regel still auslässt,
     ist genau das, was Regel 4 verbietet.

  5. **Die Startansicht öffnet auf „Review" und versteckt damit die Stufe A.**
     `INITIAL_EXPLORER_STATE.tab` steht auf `'review'` (`src/state/explorer.ts:45`) –
     eine Festlegung aus der Zeit der sechs Beispiele, als es überhaupt kein
     Stufe-A-Finding gab. Im Lauf `2026-08-28-702323b8` heißt das: wer das UI öffnet,
     sieht 98 von 208 Findings, und die 30 Stufe-A-Findings – die automatisierbaren, die
     als einzige über eine Gruppenfreigabe in einem Zug erledigt werden – liegen in einem
     Tab, den niemand angeklickt hat. Die Reihenfolge der Arbeit ist damit falsch
     vorgegeben: der teuerste Weg steht vorn, der billigste versteckt. Vorschlag: die
     Startansicht auf den ersten **nicht leeren** Tab in der Reihenfolge Massenänderung →
     Review → Entscheidung → Prozess setzen, statt auf einen festen Wert. Dann führt ein
     Lauf ohne Stufe A weiterhin nach „Review", und ein Lauf mit Stufe A beginnt dort,
     wo die Arbeit am schnellsten fertig ist.
     **Erledigt am 2026-09-02.** `startTab(findings)` in `src/lib/select-findings.ts`
     nimmt den ersten Aktionstyp aus `ACTION_TYPES`, zu dem es mindestens ein Finding
     gibt; gezählt wird ungefiltert, ein leerer Lauf bleibt bei „Review". `App.tsx`
     schickt das Ergebnis nach jedem erfolgreichen Laden hinter `reset_filters` als
     `set_tab`. `INITIAL_EXPLORER_STATE.tab` steht weiter auf `'review'` – solange kein
     Lauf geladen ist, gibt es nichts zu zählen.
  6. **Der Gruppenkopf nennt einen Buchungskreis, obwohl die Gruppe zwei umfasst.**
     `groupByRule` übernimmt als Gruppentitel den Titel des ersten Findings
     (`src/lib/sampling.ts:92`, `title: first.title`). Bei AP-COM-003 lautet der
     „Prüfung auf doppelte Rechnung nicht gesetzt (Buchungskreis 1000)" – die Gruppe
     enthält aber 23 Findings aus 1000 **und 7 aus 2000**. Freigegeben werden mit einem
     Klick alle 30. Das ist kein Schönheitsfehler: der Kopf sagt etwas anderes als die
     Freigabe tut, und der Grund ist, dass ein Freitexttitel als Beschriftung für eine
     Menge benutzt wird, die er nie beschrieben hat. Der Titel gehört zum einzelnen
     Finding, nicht zur Gruppe. Vorschlag für den Durchgang: den Gruppenkopf aus der
     Regel bilden (Regel-ID, Stufe, Anzahl) und die Buchungskreise der Gruppe daneben
     zählen – „AP-COM-003 · 30 Findings · Buchungskreise 1000, 2000". Ein Titel je
     Gruppe wäre erst wieder tragfähig, wenn der Regelkatalog ihn liefert (siehe 4.);
     bis dahin ist die Aufzählung ehrlicher als ein geliehener Satz.
     **Erledigt am 2026-09-02.** `RuleGroup` hat `title` verloren und trägt jetzt
     `companyCodes` – `companyCodeOptions(group)`, also eindeutig, sortiert und der Fall
     ohne Buchungskreis am Ende. `describeCompanyCodes` (rein, in `src/lib/sampling.ts`,
     nicht in der Komponente) macht daraus den Satzteil: „Buchungskreis 1000",
     „Buchungskreise 1000, 2000", „ohne Buchungskreis", gemischt „Buchungskreise 1000,
     ohne Buchungskreis". Der Kopf steht damit auf Regel-ID, Version, Stufe und
     Buchungskreisen. Einziger Leser von `group.title` war `RuleGroups.tsx` – weder der
     Freigabe-Dialog noch die Bereinigungsliste haben ihn angefasst. Ein eigener Titel je
     Gruppe bleibt offen, bis der Regelkatalog ihn liefert (siehe 4.).

  Beim Umbau bleibt der Fließtext überall als Rückfall stehen – ein Lauf mit alten
  Findings muss lesbar bleiben.
- **Lauf-Auswahl gehört in einen eigenen Vertrag, nicht in `FindingsSource`.** *(2026-08-30,
  aus Aufgabe 5b.)* Ein Backend kann mehrere Läufe anbieten; „welche Läufe gibt es" ist aber
  eine andere Frage als „lade diesen Lauf". Vorschlag für später: `FindingsCatalog` mit
  `listRuns(): Promise<RunSummary[]>`, dazu eine Auswahl im Datenstand-Banner. `FindingsSource`
  bleibt davon unberührt – der Schnitt ist so gelegt, dass das kein Umbau wird.
- **Zusammenführen zweier Entscheidungsstände.** *(2026-08-30, aus Aufgabe 5b. Als späterer
  Punkt vermerkt, Freigabe Victor.)* Heute ersetzt der Import. Ein Zusammenführen bräuchte eine
  Konfliktregel (jüngeres `at` gewinnt? der lokale Stand gewinnt? Rückfrage je Finding?) und
  gehört erst entschieden, wenn zwei Bearbeiter wirklich an einem Lauf sitzen.
- **Die Ranglisten vergleichen Beträge über Währungen hinweg.** *(2026-08-30, aus Aufgabe 6.)*
  Die Kacheln summieren je Währung getrennt, die Top-Liste und die Tabellensortierung
  ordnen dagegen über `impactCents`, also über den nackten Betrag ohne Währung – 1.000 CHF
  stünde damit über 999 EUR. Mit den Beispielen (nur EUR) ist das unsichtbar. Eine Reihenfolge
  über Währungen hinweg braucht entweder einen Kurs (den kein Feld liefert) oder eine
  Gruppierung der Liste je Währung; beides erst entscheiden, wenn ein Lauf zwei Währungen
  liefert.
- **`sample_reviewed` ist seit Aufgabe 7 Teil des Vertrags** – additiv, `format_version`
  bleibt 1. Ein Satz je Regelgruppe mit `outcome` (`released`/`blocked`), gezogener
  Stichprobe, den freigegebenen Findings und dem Auslöser der Sperre. Ein älterer Leser
  nennt das Feld als unbekannt und liest die Entscheidungen weiter.
- **Der Stichproben-Durchgang ist nur in seinen Teilen getestet, nicht als Klickstrecke.**
  *(2026-08-30, aus Aufgabe 7.)* `nextSampleStep`, `sampleProgress` und die beiden
  `build*`-Funktionen sind reine Logik mit Tests; die Verdrahtung in `FindingsExplorer`
  (Entscheidung → nächster Schritt → Rückfrage) prüft heute niemand automatisch, weil im
  Projekt keine Testing Library steht und die Rauchtests nur statisches Markup rendern.
  Das gilt genauso für den Sprung nach einer Einzelentscheidung seit Aufgabe 3. Wenn das
  UI Produktcode bleibt, ist eine Interaktionsebene (Testing Library oder Playwright) die
  nächste sinnvolle Investition – erst entscheiden, dann nachrüsten.

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
- **2026-08-30 · Aufgabe 5 (Belegpaar-Ansicht).** `src/lib/documents.ts` (reine Logik:
  Belegschlüssel, Zuordnung der Evidenz über die Referenz, Alles-oder-nichts-Zerlegung des
  Evidenztexts, Netting-Erkennung) und `src/components/review/DocumentPair.tsx`; der Abschnitt
  steht bei `leakage` mit mindestens zwei zuordenbaren Belegen **vor** Ist|Soll, sonst gar nicht.
  F-c41d7e9b2a60 zeigt zwei Belegkarten mit Referenz, Belegdatum und Zahldatum, den Fuzzy-Grund
  als „Warum dieses Paar", den Netting-Nachweis und den Platzhalter für den Betrag je Beleg;
  F-5e8a2c7f0b14 (Skonto, keine Belege) fällt auf die normale Karte zurück und behält seine
  Quellenlage in Ist|Soll. 199 Tests grün (neu: `documents`, vier neue in `ReviewCard.render`),
  `npm run lint` und `npm run build` ohne Befund. Zwei neue Schema-Rückmeldungen:
  `entity.documents[].{reference, document_date, cleared_on, amount, currency}` und
  `reference_kind: netting`. Nächster Schritt: Aufgabe 5b – die drei Produktcode-Punkte
  (`FindingsSource`-Adapter, Export-/Import-Format, virtualisierungsfähige Tabelle), erst danach
  Aufgabe 6 (Dashboard).
- **2026-08-30 · Aufgabe 5b (Produktcode-Nacharbeit).** Drei Punkte: `FindingsSource`-Adapter
  (`src/sources/`, `lib/load-run.ts` aufgelöst, `DEFAULT_SOURCE` als einzige Austauschstelle),
  versionierter Entscheidungs-Vertrag (`decisions.json` mit Umschlag, Export und Import im
  Datenstand-Banner, Rückfrage vor dem Ersetzen, Bericht statt stummem Verwerfen) und der
  virtualisierungsfähige Schnitt der Tabelle (konstante Spalten, `ROW_HEIGHT`, eigener
  Scrollbereich mit klebendem Kopf, `scrollToIndex`/`indexOfId`, `memo` auf der Zeile).
  Keine neue Abhängigkeit. 224 Tests grün (neu: `decisions-io` mit Rundlauf Export → Import,
  `indexOfId`, feste Zeilenhöhe im Rauchtest), `npm run lint` und `npm run build` ohne Befund.
  Nächster Schritt: Aufgabe 6 – Dashboard (bringt sein eigenes `overflow-y-auto` mit).
- **2026-08-30 · Aufgabe 6 (Dashboard).** `src/lib/dashboard.ts` (reine Logik: Zähler,
  Summen je Währung, Kategorien, Stufenverteilung, Top-Liste) und
  `src/components/dashboard/` (Kachelrahmen, Euro-Wirkung je Kategorie, Verteilung nach
  Stufe, Top-Liste, Ansicht mit eigenem Scrollbereich). Die Zahlen stimmen mit der Spec
  überein: 73.042,40 € gesamt, Geldabfluss 36.812,40 €, Validität 27.300,00 €, Konsistenz
  8.930,00 €, Dublette ohne Betrag; Stufen A 0 / B 3 / C 2 / Entscheidung 1. Ein Klick in
  der Top-Liste springt über `focus_finding` in die Liste und öffnet die Karte; war eine
  Filterung eingestellt, sagt der Explorer es kurz. Score bleibt Platzhalter. 246 Tests grün
  (neu: `dashboard`, `Dashboard.render`, vier neue in `explorer`), `npm run lint` und
  `npm run build` ohne Befund. Nächster Schritt: Aufgabe 7 – Stichproben-Freigabe und Export
  (Bereinigungsliste CSV; `decisions.json` steht seit 5b, `sample_reviewed` kommt additiv dazu).
- **2026-08-30 · Aufgabe 7 (Stichproben-Freigabe und Bereinigungsliste).** `src/lib/sampling.ts`
  (Regelgruppen, Seed aus Lauf und Regel, Ziehung, Stand und Ausgang der Stichprobe,
  Freigabe- und Sperrsätze), `src/lib/cleanup-csv.ts` (Bereinigungsliste), `src/state/samples.ts`,
  `RuleGroups` und `ReleaseGroupDialog` im Explorer, `sample_reviewed` im Entscheidungs-Vertrag,
  zweiter Sicherungsknopf im Datenstand-Banner. Freigabe setzt `in_progress`, eine Ablehnung
  in der Stichprobe sperrt die Gruppe für den Lauf, Schadensklasse 1 bleibt außen vor.
  Mit den Beispielen gibt es keine Stufe-A-Gruppe: der Tab Massenänderung zeigt den
  Leerzustand mit Erklärung, der CSV-Knopf ist gesperrt. Zusätzlich der Balken der
  Stufenverteilung gestrichen (Freigabe Victor), der Bruch bleibt. 291 Tests grün
  (neu: `sampling`, `cleanup-csv`, `samples`, `RuleGroups.render`, sieben neue in
  `explorer` und `decisions-io`), `npm run lint` und `npm run build` ohne Befund.
  Nächster Schritt: Testlauf mit zwei Buchhaltern (Zeit je Entscheidung, Rückfragen,
  Missverständnisse) und Merge-Vorbereitung – Schema-Rückmeldungen gehen als Aufgabe an
  die Engine-Session, nicht von hier aus ins Schema.
- **2026-08-31 · Rebase auf Sprint 3 und Nachzug auf Schema 1.1.** `git rebase main`
  (main auf `0bf3b63`, Sprint 3 Aufgabe 5); wie erwartet genau ein Konflikt, in
  `ui/README.md`, beide Seiten übernommen. Danach war ein Test rot – der Driftschutz lief
  in „Pfad im Schema nicht gefunden", weil Schema 1.1 die Enums nach `$defs` gezogen hat;
  das ist genau der Umbau, den dieser Durchgang nachzieht. `src/types/finding.ts` steht
  jetzt auf 1.1 (alle Felder aus D-069 optional, `relevance` auf `open_items`/`volume_12m`
  + `currency`, `title` Pflicht), `run.json` ist als Lauf-Kopf angebunden („Findings-Datei
  laden" nimmt beide Dateien), `build-data.mjs` ist als Ersatz für die sechs Beispiele
  kenntlich gemacht, und die Spec-Zeile zur Gruppenfreigabe steht auf `in_progress`.
  312 Tests grün (vorher 291; neu: `file-source` mit 10 und `parse`/`finding.enums` mit 7),
  `npm run lint` und `npm run build` ohne Befund. Handprobe am echten Lauf
  `2026-08-28-702323b8`: Banner „16 Tabellen", Buchungskreise 1000 und 2000, 30 Findings
  (AR-VAL-001 15, AR-CON-002 7, AP-LEA-001 8), C:0000101502 mit Volumen 12 Monate
  8.930,00 €, keine Konsolenfehler. Nächster Schritt: die Karte auf die Felder aus D-069
  verdrahten, sobald die Engine sie füllt – bis dahin bleibt der Fließtext der Rückfall.
- **2026-09-01 · Schlusshandprobe Sprint 3 am 208er-Lauf.** Derselbe Lauf-Ordner
  `2026-08-28-702323b8`, aber der Stand vom 31.08.: 208 Findings aus 17 Regeln statt 30
  aus 3. Über „Findings-Datei laden" `findings.json` + `run.json` geladen, nichts
  angepasst. Es stimmt: Banner „16 Tabellen" und Buchungskreise 1000/2000; 208 Findings
  in den Tabs 30/98/72/8; die Verteilung je Regel deckt sich in **allen 17** Regeln mit
  `run.json`/`report.txt` (AR-HYG-001 40, AP-COM-003 30, AP-HYG-001 25, AR-COM-002 20 …);
  `entity.display_name` überall gefüllt; C:0000101502 mit Volumen 12 Monate 8.930,00 €;
  AP-COM-003 als Stufe A mit „Massenänderung" und Chip „massenänderungsfähig";
  CROSS-DUP-001 mit beiden Konten in `entity.records`; AR-LEA-001 mit dem Beleg in
  `entity.documents`; Freitext durchgehend deutsch, Datenfelder ISO, kein Float im JSON;
  Stufen A 30 / B 59 / C 47 / E 72, Schadensklasse 1 nie Stufe A; keine Konsolenfehler
  über sechs geöffnete Karten und drei Ansichten. Gemeldet statt gefixt: die vier
  Arbeiten des Verdrahtungsdurchgangs (Vergleich aus `records` statt aus `current.value`,
  Bedingung `records` statt `category`, Belegkarte auch für einen Beleg, Regeln-Ansicht
  aus `run.json.rules`), die Engine-Abhängigkeit AP-LEA-001 v1.1 und der Sprint-4-Entscheid
  zu `impact_eur`. Aus Victors eigenem Durchgang in Tab 1 kamen zwei weitere Punkte dazu:
  die Startansicht öffnet auf „Review" und lässt die 30 Stufe-A-Findings ungesehen, und
  der Gruppenkopf im Tab Massenänderung nennt einen Buchungskreis für eine Gruppe, die
  zwei umfasst und in einem Klick freigegeben wird. Gefixt wurde nur ein Anzeigefehler: bei mehreren widersprechenden
  Evidenzeinträgen stand „2 Einträge widersprechen dem Soll und **steht** zuerst" – der
  Satz wird jetzt ganz in den Plural gesetzt, mit einem Test je Form.
  314 Tests grün, `npm run lint` und `npm run build` ohne Befund.
  Nächster Schritt: Pause bis zum Verdrahtungsdurchgang.
- **2026-09-02 · Mini-Commit nach Absturz neu gebaut.** Die zwei Punkte aus der
  Tab-1-Handprobe waren umgesetzt, aber nicht auf der Platte: Arbeitsverzeichnis sauber,
  kein Stash, nichts unpushed. Also neu gebaut, nach Victors geprüfter Fassung:
  `startTab` in `select-findings.ts` plus `set_tab` nach dem Laden in `App.tsx`, und
  `RuleGroup.title` → `companyCodes` mit `describeCompanyCodes` für den Gruppenkopf.
  324 Tests grün (vorher 314; neu: drei zu `startTab`, drei zu `companyCodes` in
  `groupByRule`, drei zu `describeCompanyCodes`, einer im Rauchtest der Regelgruppen),
  `tsc -b` und `oxlint` ohne Befund. Nächster Schritt: unverändert der
  Verdrahtungsdurchgang mit den Arbeiten 1 bis 4.
