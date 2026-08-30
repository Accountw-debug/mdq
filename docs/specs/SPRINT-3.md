# Sprint 3 – Schema-Erweiterungen, Staging, Mapping, `mdq run`, Regression scharf

Ziel: Aus SE16N-Exports entstehen zum ersten Mal echte Findings. `mdq run` läuft Ende-zu-Ende
auf dem Demo-Mandanten, die Regression aus Sprint 2 ist scharf, und 14 weitere Regeln sind
gebaut. Dubletten (AR-DUP-001, AP-DUP-001) bleiben Sprint 4 – sie erscheinen in der
Regression weiter als „Regel fehlt".

## Aufgabe 0 – Schema-Erweiterungen aus dem UI (ein eigener Commit vor allem anderen)

Gesammelte Rückmeldungen des UI-Stroms; Schema-Version anheben, GLOSSARY ergänzen,
die sechs Beispiel-Findings dort erweitern, wo die Daten existieren:

1. `evidence[].reference_kind` (optional, enum): `document | master_field | cluster | external_query | statement | netting | payment_run | policy`. Der Netting-Nachweis in F-003 bekommt `netting` – das UI erkennt ihn dann am Feld statt an der Formulierung.
2. `entity.documents[]` erweitert (alle optional): `reference`, `document_date`, `cleared_on`, `amount` (String, 2 Dezimalen), `currency`. F-003 wird damit vollständig (32.000,00 je Beleg).
3. `entity.records` (optional, für `duplicate`-Findings): je beteiligtem Konto ein strukturierter Datensatz `{bp_key, fields: {name, street, postal_code, city, country, vat_id, iban_masked, payment_terms, open_items, currency, last_activity_on}}`. Beträge als String, IBAN nur maskiert (`DE44 …49 32`). F-002 bekommt beide Konten.
4. `proposed.golden_record` (optional, für `duplicate`): je Feld der beste Wert mit Quelle: `{field: {value, source_bp_key, source_type}}` – löst das Glossar-Versprechen „je Feld der beste Wert" ein. F-002 exemplarisch füllen.
5. Prüfen, dass `decision.assigned_to` und die `title`-Pflicht aus den früheren Commits im Schema und in allen sechs Beispielen konsistent sind.

Akzeptanz: `mdq validate logic/examples/findings/` 6/6; ein Negativtest je neuem Feld
(falscher enum-Wert, Betrag als float in `documents`, `records` mit unbekanntem Feld).

## Aufgabe 1 – Staging: raw → staged (typisiert)

- Je Tabelle aus dem Mapping: Spalten typisieren über `formats.py`; Fehler → `reject` (Stufe staged) mit Grund, Lauf bricht nicht ab.
- **Notationserkennung je Datei (D-035):** aus den eindeutigen Beträgen der Datei die Notation (de/iso) bestimmen und auf mehrdeutige (`1.234`) anwenden; keine eindeutigen Werte → `--decimal-notation de|iso`, sonst Reject. Prozentfelder nach Feldtyp, nicht nach Datei-Notation (D-048).
- `reference_norm` = `upper(regexp_replace(XBLNR, '[^A-Za-z0-9]', ''))` (D-065), `iban_norm`, `value_norm` für Steuer-IDs.
- SAP-Initialwerte → NULL (D-032/D-033); `amount_signed_local` genau hier aus SHKZG (D-009).
- Kontrollsummen in den Run-Report: Zeilen raw vs. staged je Tabelle, Summe `amount_signed_local` je Tabelle und Buchungskreis.

## Aufgabe 2 – Kanonisches Mapping: staged → canonical

- Umsetzung von `logic/mappings/sap_ecc.yaml`: `business_partner` (KNA1/LFA1 inkl. `tax_id.*`-Aufspaltung nach `bp_tax_id`), `bp_company_code`, `bp_bank_account` mit TIBAN-Join, `bp_partner_function`, `bp_dunning`, `payment_terms` mit T052U-Text (SPRAS DE bevorzugt), `fi_item` (is_open aus Quelltabelle, `item_key`).
- `bp_key`-Ableitung mit Rollenpräfix, `alt_payer_key` mit Präfix.
- Scoping: `--company-codes`, `--side ar|ap|both`, Postenfenster aus `run_meta.scope`.
- ADR6-E-Mails, wenn geliefert (Join über `address_id`).
- Referentielle Prüfung: Posten ohne Stammsatz → Reject (canonical) mit Grund.

## Aufgabe 3 – BP-360: `bp_relevance` + Hauswährung + Gedächtnis

- `bp_relevance` materialisieren nach den Glossar-Definitionen: `open_items_local`, `volume_12m_local` (Rechnungen brutto minus Gutschriften, 12 Monate vor data_as_of, unabhängig vom Ausgleich), `last_activity_on` (Max aus Buchungs- und Ausgleichsdatum), `activity_status`, `currency`.
- Hauswährungsprüfung (D-030): mehrere Währungen im Scope → Abbruch mit der bestehenden Meldung; `--company-codes` funktioniert jetzt wirklich.
- `decision_memory` wird vor der Regelausführung gelesen: Findings, deren `finding_id` dort mit `intentionally_separate | data_correct | not_relevant | accepted_risk` steht, werden erzeugt, aber mit dem gespeicherten Status ausgegeben statt `open` (Whitelist wirkt, nichts verschwindet stumm).

## Aufgabe 4 – `mdq run` Ende-zu-Ende

- `mdq run --input <dir> --out runs/ [--company-codes …] [--side …] [--decimal-notation …] [--data-as-of JJJJ-MM-TT]`.
- Ablauf: load → stage → map → relevance → Regeln → Findings validieren → schreiben.
- Ausgaben in `runs/<run_id>/`: `findings.json` (Array, nach finding_id sortiert), `run.json` (= `RunReport.to_dict()` plus Scope und Versionen – das Format, das das UI lädt), `report.txt` (Render). `run_id` = `<data_as_of>-<kurzhash der Input-Hashes>`, deterministisch.
- Exit-Codes: 0 sauber, 1 Findings mit Auffälligkeiten im Lauf (Rejects/übersprungene Regeln), 2 Abbruch (Währung, fehlende Pflichtdateien). Der Stolperdraht-Test aus Sprint 2 wird jetzt bewusst angefasst.
- Laufzeit auf dem Demo-Mandanten unter 60 Sekunden.

## Aufgabe 5 – Regression scharf

- Skip entfernen; `mdq run` auf `testdata/demo_mandant`, Vergleich über `regression.py`.
- Erwartetes Endbild dieses Sprints: **0 fehlend, 0 unerwartet, 0 abweichend; Hinweise: 2 bekannt offen (AP-LEA-001 v1.1), 20 „Regel fehlt" (AR-DUP-001 12, AP-DUP-001 8).**
- Jede Abweichung wird einzeln geklärt: Regel falsch, Generator falsch oder Erwartung falsch – Stopp und Victor fragen (Regel 1), nie stillschweigend anpassen.

## Aufgaben 6–8 – die 14 Regeln, in drei Paketen (je Paket ein Commit)

Reihenfolge innerhalb: Regel bauen → Klartext prüfen → `hits/no_hits/edge` aus defects.yaml → Regression laufen lassen.

- **6 · AR-Stammdaten:** AR-COM-002 (Soll = dominante ZTERM aus Belegen, Stufe B), AR-VAL-002 (inkl. Hinweis „sieht wie deutsche Steuernummer aus – gehört in STCD1", D-058), AR-VAL-003 (IBAN-Prüfziffer, SK 1, Stufe C), AR-VAL-005 (Platzhalternamen), AR-HYG-001 (Fensterdefinition D-057).
- **7 · AP-Seite:** AP-VAL-001, AP-VAL-002, AP-VAL-003, AP-CON-001 (gleiche IBAN, Regulierer-Ausschluss), AP-COM-003 (REPRF, Stufe A, mass_change), AP-HYG-001, AP-LEA-002 (Skontoverlust, process, Rechnung offen ausweisen).
- **8 · Übergreifend:** CROSS-DUP-001 (gleiche USt-ID, deterministisch – kein Fuzzy nötig), AR-LEA-001 (Akontozahlungen, finding_key = Belegnummer).

## Aufgabe 9 – Kleinigkeiten mit Vertragswirkung

- `demo_mandant_chf/`: Mini-Mandant (ein Buchungskreis, CHF, 20 BPs) nur für den D-030-Abbruchtest.
- `mdq demo generate` erhält `--no-defects` wirklich (D-059 verweist darauf).
- `docs/extraction/SAP-ECC-EXTRACTION.md` gegen das tatsächlich implementierte Mapping prüfen (Felder, die das Staging braucht, müssen in der Anleitung stehen).

## Victors Teil (parallel, unverändert offen)
- Defekt-Einträge für weitere Findings aus der Praxis in `defects.yaml` (je Eintrag ein Beispiel-Finding in `logic/examples/`).
- Katalog: Status `spec → impl` wandert automatisch über die Tests; offene Katalogfragen von Sprint 2 beantworten, falls noch offen.

## Definition of Done Sprint 3
Regression exakt im Endbild von Aufgabe 5 · `mdq run` unter 60 s, Exit-Codes wie definiert ·
`runs/<id>/run.json` + `findings.json` laden im UI über „Findings-Datei laden" (Handprobe) ·
alle neuen Regeln mit Testfällen, Katalog konsistent · DECISIONS je Aufgabe · keine
Geschäftspartnerdaten in Logs · Läufe deterministisch (zweimal `mdq run` → identische Dateien).

## Nicht in Sprint 3
Dubletten mit Fuzzy (Sprint 4), Euro-Wirkung Doppelzahlung über Konten (v1.1, Sprint 4),
KI-Schicht (4b), VIES/Anreicherung, Score, Delta zwischen Läufen.
