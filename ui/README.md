# ui/

UI von MDQ (Vite + React + TypeScript + Tailwind + shadcn/ui), Sprint 5.
Liest ausschließlich Findings-JSON (`runs/<run_id>/findings.json`, D-007). Kern-Screens:
Dashboard, Findings-Explorer nach Aktionstyp, Review-Karte mit Evidenz-Panel,
Dubletten-Vergleich, Belegpaar-Ansicht. Leitlinien: `docs/CONCEPT.md` Abschnitt 9.

Das ist finaler Produktcode, kein Prototyp (D-063) – dieselbe Sorgfalt wie in `logic/` und
`engine/`. Design zählt, der Code aber genauso: er wird nicht später ersetzt.

Auth und Mehrbenutzerbetrieb sind spätere Sprints, nicht gestrichen.
