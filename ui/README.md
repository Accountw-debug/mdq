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

`scripts/build-data.mjs` liest `../logic/examples/findings/*.yaml` und schreibt
`public/data/findings.json` und `public/data/run.json`. Beide sind Build-Artefakte
und nicht eingecheckt. Fehlt ein Pflichtfeld, ist eine `finding_id` doppelt oder
gehören die Findings zu verschiedenen Läufen, bricht das Skript ab – nichts wird
stumm übersprungen.

Eine andere Quelle (z. B. ein echter Lauf der Engine) über die Umgebungsvariable:

```
MDQ_FINDINGS_DIR=../runs/demo-2026-08-30 npm run data
```

## Aufbau

```
scripts/build-data.mjs     YAML -> JSON, Pflichtfeldprüfung, Lauf-Kopf
src/types/finding.ts       Typen zu logic/finding.schema.json (Enums als Union-Types)
src/lib/format.ts          deutsche Beträge/Daten, Cent-Arithmetik über bigint
src/components/Key.tsx     Monospace für Schlüssel, Belegnummern, Feldnamen
src/components/ui/         shadcn/ui, generiert – nicht von Hand umbauen
```
