# Regeln – Format und Vertrag

Eine Regel = eine Datei `<ID>.rule.sql`. ID-Format `<SEITE>-<KAT>-<NNN>`:
Seite `AR|AP|CROSS`, Kategorie `COM` (completeness) `VAL` (validity) `CON` (consistency)
`HYG` (hygiene) `RSK` (risk) `DUP` (duplicate) `LEA` (leakage).

## Aufbau

```sql
/* ---
id: AR-VAL-001
version: "1.0"
title: "..."                       # Kurzüberschrift, darf {params} enthalten
side: AR
category: validity
severity: high
damage_class: 2
default_tier: B
default_action_type: review
requires_tables: [business_partner, bp_tax_id]
plain_logic: >                     # Klartext – muss dem SQL entsprechen (Regel 10 in CLAUDE.md)
  ...
why: >                             # Klartext für den Kunden, darf {params} enthalten
  ...
if_wrong: >
  ...
remediation:
  sap_transaction: XD02
  path: "Steuerung → USt-IdNr."
  field: STCEG
  mass_change_eligible: false
tests:                             # Testfälle gegen testdata/demo_mandant (Regression) – nie an Code anpassen
  hits:     [ "C:0000100234" ]     # muss treffen
  no_hits:  [ "C:0000100001" ]     # darf nicht treffen
  edge:     [ "C:0000100777" ]     # Grenzfall, Erwartung im Kommentar
--- */
SELECT ... ;
```

## Ausgabe-Vertrag des SQL (Spalten)

| Spalte | Pflicht | Bedeutung |
|---|---|---|
| `bp_key`, `role` | ja | Betroffener BP |
| `company_code` | nein | Buchungskreis, falls BUKRS-bezogen |
| `source_table`, `source_field`, `current_value` | ja | Ist |
| `current_display` | nein | Lesbare Darstellung des Ist |
| `proposed_value`, `proposed_display`, `source_summary` | nein | Soll + Quellenlage (Pflicht bei Stufe A/B) |
| `options` | nein | JSON-Array `[{label, consequence}]` bei `decision` |
| `tier`, `action_type` | nein | Überschreiben die Defaults aus dem Kopf (dynamisch je Zeile) |
| `evidence` | nein | JSON-Array `[{source_type, reference, value, observed_at, agrees, note}]` |
| `impact_amount`, `impact_currency`, `impact_formula`, `netted_against` | nein | Euro-Wirkung; `impact_amount` als DECIMAL(15,2) |
| `related_bp_keys` | nein | JSON-Array weiterer BP-Schlüssel |
| `documents` | nein | JSON-Array `[{company_code, fiscal_year, document_no, line_item}]` |
| `params` | nein | JSON-Objekt für Platzhalter in `title`, `why`, `if_wrong` |
| `finding_key` | nein | Zusätzliches Unterscheidungsmerkmal für die `finding_id`, wenn `bp_key` + Feld + Ist nicht eindeutig sind (z. B. Belegpaar) |

Die Engine ergänzt: `finding_id`, `run_id`, Versionen, `relevance` aus `bp_relevance`,
`status = open`, `data_as_of`, `created_at` – und validiert gegen `logic/finding.schema.json`.

Die `finding_id` ist `F-` + die ersten 12 Zeichen von sha1 über

```
rule_id | bp_key | company_code | source_table | source_field | current_value | finding_key
```

mit `|` als Trenner und leerem Text für `NULL`. `company_code` und `finding_key` gehören
dazu, weil eine Regel mehrere Findings je Geschäftspartner liefern kann (je Buchungskreis
bzw. je Belegpaar); ohne sie würden die Findings kollidieren. Eine Kollision innerhalb
eines Laufs ist ein Fehler – dann fehlt der Regel ein `finding_key`.

## Regeln für Regeln

- Nur kanonisches Schema lesen (`logic/schema/canonical.sql`), nie Raw/Staged.
- CpD-Konten (`is_one_time`) in Dubletten- und den meisten Stammdatenregeln ausschließen.
- Schadensklasse 1 (Bankdaten): `default_tier` darf nie `A` sein, `mass_change_eligible: false`.
- Deterministisch sortieren (`ORDER BY bp_key, ...`), damit Findings über Läufe stabil bleiben.
- Jede Regel hat mindestens je einen `hits`- und `no_hits`-Testfall im Demo-Mandanten.
