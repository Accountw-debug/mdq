# Entscheidungslog

Format: `D-NNN · Datum · Entscheidung · Grund · Verworfene Alternativen`

- **D-001 · 2026-08-30 · Logik und Code strikt trennen.** `logic/` (Schema, Regeln, Mappings, Wörterbücher) ist technologieunabhängig; `engine/` und `ui/` sind austauschbar. Grund: Neubau mit anderer Technologie soll nur die Engine kosten. Alternative verworfen: Regeln im Python-Code.
- **D-002 · 2026-08-30 · Regeln sind SQL auf dem kanonischen Schema, ausgeführt in DuckDB.** Grund: SQL ist die portabelste Logik (HANA, Databricks, Postgres). Alternative verworfen: Pandas-Pipelines, Python-Prädikate.
- **D-003 · 2026-08-30 · Dateibasierte Extraktion (SE16N/FBL-Exports) für V1.** Grund: kein Connector-Betrieb, kein Transport beim Kunden, passt zu On-Prem. RFC/OData erst mit Monitoring.
- **D-004 · 2026-08-30 · Stufenmodell A/B/C/decision mit Präzisionszielen 99/90 %.** Grund: Abdeckung über Quellen, nie über niedrigere Schwellen. Alternative verworfen: eine globale Konfidenzschwelle.
- **D-005 · 2026-08-30 · Schadensklasse 1 (Bankdaten) wird nie Stufe A.** Grund: falsche IBAN = Fehlüberweisung, Betrugsvektor. Keine Ausnahme per Policy.
- **D-006 · 2026-08-30 · Prototyp-Engine darf später neu gebaut werden.** `logic/`, `testdata/` und das UI-Design bleiben. Grund: Victor baut solo mit Claude Code vor; Lux baut die Produkt-Engine.
- **D-007 · 2026-08-30 · UI liest ausschließlich Findings-JSON.** Grund: UI und Engine parallel entwickelbar, Vertrag ist das Schema.
- **D-008 · 2026-08-30 · Keine echten Kundendaten im Repo, nie.** Nur Demo-Mandant und Encoding-Samples. `data/` und `runs/` ignoriert.
- **D-009 · 2026-08-30 · Geldbeträge als DECIMAL(15,2), Schlüssel als Text mit führenden Nullen.** Grund: Float-Rundung und ALPHA-Konvertierung sind die häufigsten Fehlerquellen bei SAP-Daten.
- **D-010 · 2026-08-30 · Golden Dataset als Regression.** Demo-Mandant + `testdata/expected/` sind Spec und Test; erwartete Ergebnisse werden nie an Code angepasst.
