# ui/

UI von MDQ (Vite + React + TypeScript + Tailwind + shadcn/ui), Sprint 5.
Liest ausschließlich Findings-JSON (`runs/<run_id>/findings.json`, D-007). Kern-Screens:
Dashboard, Findings-Explorer nach Aktionstyp, Review-Karte mit Evidenz-Panel,
Dubletten-Vergleich, Belegpaar-Ansicht. Leitlinien: `docs/CONCEPT.md` Abschnitt 9.

Das ist finaler Produktcode, kein Prototyp (D-063) – dieselbe Sorgfalt wie in `logic/` und
`engine/`. Design zählt, der Code aber genauso: er wird nicht später ersetzt.

Auth und Mehrbenutzerbetrieb sind spätere Sprints, nicht gestrichen.

Entscheidungen, offene Fragen und Schema-Rückmeldungen: `ui/NOTES.md`.

## Befehle

```
npm install                # Abhängigkeiten (Node >= 20)
npm run dev                # Daten bauen + Entwicklungsserver auf http://localhost:5173
npm run build              # Daten bauen + Typprüfung + Produktionsbuild nach dist/
npm run test               # vitest (Formatierer, Enum-Abgleich gegen das Schema)
npm run lint               # oxlint
npm run data               # nur public/data/{findings,run}.json neu erzeugen
```

## Daten

Der Normalfall ist ein Lauf der Engine: `uv run mdq run --input <dir> --out runs/`
schreibt `runs/<run_id>/findings.json` und `runs/<run_id>/run.json`. Beide Dateien
werden im Datenstand-Banner über „Findings-Datei laden" **zusammen** gewählt. Erst
mit `run.json` stimmen Tabellenzahl und Buchungskreise: sie beschreiben den Lauf,
nicht die Findings – ein Buchungskreis ohne Befund gehört trotzdem in den Datenstand.
Ohne `run.json` wird der Kopf aus den Findings abgeleitet und `tables_loaded` bleibt 0.
Die Dateien bleiben im Speicher; nichts wird im Browser abgelegt.

`scripts/build-data.mjs` ist der **Ersatz für die sechs Beispiel-Findings**, kein
Lauf: es liest `../logic/examples/findings/*.yaml` und schreibt
`public/data/findings.json` und `public/data/run.json`, damit die Anwendung auch
ohne Engine-Lauf etwas anzuzeigen hat. Dort steht `tables_loaded: 0` ausdrücklich
für „kein Engine-Lauf". Beide Dateien sind Build-Artefakte und nicht eingecheckt.
Fehlt ein Pflichtfeld, ist eine `finding_id` doppelt oder gehören die Findings zu
verschiedenen Läufen, bricht das Skript ab – nichts wird stumm übersprungen.

Ein anderes Verzeichnis mit Beispiel-YAML über die Umgebungsvariable:

```
MDQ_FINDINGS_DIR=../logic/examples/findings npm run data
```

## Aufbau

```
scripts/build-data.mjs     YAML -> JSON, Pflichtfeldprüfung, Ersatz-Lauf-Kopf
src/sources/               FindingsSource: Beispiel-Daten oder gewählte Lauf-Dateien
src/types/finding.ts       Typen zu logic/finding.schema.json 1.1 (Enums als Union-Types)
src/lib/format.ts          deutsche Beträge/Daten, Cent-Arithmetik über bigint
src/components/Key.tsx     Monospace für Schlüssel, Belegnummern, Feldnamen
src/components/ui/         shadcn/ui, generiert – nicht von Hand umbauen
```
