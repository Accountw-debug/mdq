# Regelkatalog v0.1 – Victors fachlicher Arbeitsstand

Jede Zeile wird zu einer Datei `logic/rules/<ID>.rule.sql`. Status: `draft` (nur Zeile),
`spec` (Klartext + Testfälle fertig, Victor freigegeben), `impl` (SQL + Tests grün).
Schwere: low/medium/high/critical · Schadensklasse: 1 Bankdaten / 2 steuerlich-vertraglich / 3 reversibel
· Stufe: A/B/C/decision · Aktion: mass_change/review/decision/process

Spalte `Testdaten`: `Defekt` heisst, `testdata/demo_mandant/defects.yaml` erzeugt fuer diese
Regel mindestens einen Fall; `ohne Testfall` heisst, der Demo-Mandant kennt sie noch nicht.
Die Spalte wird von `engine/tests/test_catalog.py` gegen die Defektliste geprueft und ist von
Hand nachzuziehen, wenn ein Defekt dazukommt (D-066).

Hinweis: `mass_change` setzt Stufe A voraus. Bei Regeln, die per Policy automatisierbar sind
(AR-HYG-001, AP-HYG-001), steht im Regelkopf der konservative Default `decision`/`decision`;
die Policy hebt zur Laufzeit Stufe **und** Aktion gemeinsam an.

## AR – Debitoren

| ID | Titel | Kategorie | Schwere | SK | Stufe | Aktion | Tabellen | SAP | Status | Testdaten |
|---|---|---|---|---|---|---|---|---|---|---|
| AR-COM-001 | USt-ID fehlt bei EU-B2B-Debitor (Land ≠ DE oder Kontengruppe B2B) | completeness | high | 2 | C | review | business_partner, bp_tax_id | XD02 Steuerung | draft | ohne Testfall |
| AR-COM-002 | Zahlungsbedingung im Buchungskreis leer | completeness | medium | 2 | B mit Mehrheit auf den Belegen, sonst C | review | bp_company_code, fi_item, payment_terms | XD02 Zahlungsverkehr | impl | Defekt |
| AR-COM-003 | Bankverbindung fehlt bei Zahlweg Lastschrift | completeness | high | 1 | C | review | bp_company_code, bp_bank_account | XD02 Zahlungsverkehr | draft | ohne Testfall |
| AR-COM-004 | Mahnverfahren leer bei aktivem Debitor | completeness | medium | 3 | A (Soll = Standardverfahren laut Policy) | mass_change | bp_company_code, bp_relevance | XD02 Korrespondenz | draft | ohne Testfall |
| AR-VAL-001 | USt-ID-Präfix passt nicht zum Sitzland | validity | high | 2 | B | review | business_partner, bp_tax_id | XD02 | impl | Defekt |
| AR-VAL-002 | USt-ID entspricht nicht dem Länderformat | validity | high | 2 | C | review | bp_tax_id (+ vat_id_patterns) | XD02 | impl | Defekt |
| AR-VAL-003 | IBAN-Prüfziffer ungültig | validity | critical | 1 | C | review | bp_bank_account | XD02 | impl | Defekt |
| AR-VAL-004 | PLZ entspricht nicht dem Länderformat | validity | low | 3 | B | review | business_partner (+ postal_code_patterns) | XD02 Adresse | draft | ohne Testfall |
| AR-VAL-005 | Name/Ort enthält Platzhalter ("Test", "unbekannt", "???", "xxx") | validity | medium | 3 | C | review | business_partner (+ placeholder_terms) | XD02 Adresse | impl | Defekt |
| AR-CON-001 | Zahlungsbedingung Stamm ≠ meistgenutzte auf Belegen (>70 % abweichend) | consistency | medium | 2 | B | review | bp_company_code, fi_item | XD02 | draft | ohne Testfall |
| AR-CON-002 | Löschvormerkung/Sperre bei offenen Posten | consistency | high | 3 | decision | decision | business_partner, bp_company_code, fi_item | XD05/XD06 | impl | Defekt |
| AR-CON-003 | IBAN-Land ≠ Sitzland (Hinweis, kein Fehler) | consistency | low | 1 | C | review | business_partner, bp_bank_account | – | draft | ohne Testfall |
| AR-CON-004 | Gleiche IBAN bei mehreren Debitoren ohne Regulierer-Bezug | consistency | high | 2 | B | review | bp_bank_account, bp_partner_function | XD02 | draft | ohne Testfall |
| AR-HYG-001 | Kein Posten im gesamten Postenfenster, Anlage vor Fensterbeginn, keine OP (Löschkandidat) | hygiene | low | 3 | decision (Policy kann zur Laufzeit auf A heben) | decision | business_partner, bp_relevance | XD06 | impl | Defekt |
| AR-HYG-002 | Angelegt im Postenfenster, älter als 12 Monate, nie bebucht | hygiene | low | 3 | decision | decision | business_partner, bp_relevance | XD06 | draft | ohne Testfall |
| AR-DUP-001 | Dubletten-Cluster (Name+Adresse normalisiert, USt-ID, IBAN) | duplicate | high | 2 | B | review | business_partner, bp_tax_id, bp_bank_account, bp_partner_function | XD05/XD06/FB05 | draft | Defekt |
| AR-LEA-001 | Unapplied Cash: Zahlungseingänge ohne Rechnungsbezug (Akonto) älter 30 Tage | leakage | medium | 3 | B | review | fi_item | F-32 | draft | Defekt |
| AR-LEA-002 | Umbuchungen zwischen Debitoren (Hinweis auf Fehlzuordnung/Dublette) | leakage | medium | 3 | C | review | fi_item | – | draft | ohne Testfall |
| AR-LEA-003 | Skonto gewährt, obwohl Skontofrist überschritten | leakage | medium | 2 | B | review | fi_item, payment_terms | – | draft | ohne Testfall |

## AP – Kreditoren

| ID | Titel | Kategorie | Schwere | SK | Stufe | Aktion | Tabellen | SAP | Status | Testdaten |
|---|---|---|---|---|---|---|---|---|---|---|
| AP-COM-001 | USt-ID fehlt bei EU-Lieferant | completeness | high | 2 | C | review | business_partner, bp_tax_id | XK02 | draft | ohne Testfall |
| AP-COM-002 | Bankverbindung fehlt bei Zahlweg Überweisung | completeness | high | 1 | C | review | bp_company_code, bp_bank_account | XK02 | draft | ohne Testfall |
| AP-COM-003 | Prüfung doppelte Rechnung (REPRF) nicht gesetzt | completeness | high | 3 | A | mass_change | bp_company_code | XK02 Zahlungsverkehr | draft | Defekt |
| AP-VAL-001 | USt-ID-Präfix passt nicht zum Sitzland | validity | high | 2 | B | review | wie AR-VAL-001 | XK02 | draft | Defekt |
| AP-VAL-002 | USt-ID entspricht nicht dem Länderformat | validity | high | 2 | C | review | bp_tax_id | XK02 | draft | Defekt |
| AP-VAL-003 | IBAN-Prüfziffer ungültig | validity | critical | 1 | C | review | bp_bank_account | XK02 | draft | Defekt |
| AP-CON-001 | Gleiche IBAN bei mehreren Kreditoren | consistency | critical | 1 | C | review | bp_bank_account | XK02 | draft | Defekt |
| AP-CON-002 | IBAN-Land ≠ Sitzland bei Kreditor | consistency | medium | 1 | C | review | business_partner, bp_bank_account | – | draft | ohne Testfall |
| AP-CON-003 | Zahlung an gesperrten/zur Löschung vorgemerkten Kreditor (letzte 12 Monate) | consistency | high | 3 | C | review | business_partner, bp_company_code, fi_item | – | draft | ohne Testfall |
| AP-HYG-001 | Kein Posten im gesamten Postenfenster, Anlage vor Fensterbeginn (Löschkandidat) | hygiene | low | 3 | decision (Policy kann zur Laufzeit auf A heben) | decision | business_partner, bp_relevance | XK06 | draft | Defekt |
| AP-RSK-001 | Bankdatenänderung kurz vor Zahlung (< 30 Tage) ohne Vier-Augen (V2: CDHDR) | risk | critical | 1 | C | process | change_document, fi_item | – | draft | ohne Testfall |
| AP-DUP-001 | Kreditoren-Dubletten-Cluster | duplicate | high | 2 | B | review | business_partner, bp_tax_id, bp_bank_account | XK05/XK06 | draft | Defekt |
| AP-LEA-001 | Mögliche Doppelzahlung (Referenz fuzzy, gleicher Betrag, 60 Tage) | leakage | critical | 2 | B | review | business_partner, fi_item | FBL1N | impl | Defekt |
| AP-LEA-002 | Skontoverlust je Kreditor (12 Monate) | leakage | medium | 3 | C | process | fi_item, payment_terms | F110 | draft | Defekt |
| AP-LEA-003 | Überzahlung: Zahlung > Rechnungsbetrag ohne Gutschrift | leakage | high | 2 | B | review | fi_item | – | draft | ohne Testfall |

## CROSS

| ID | Titel | Kategorie | Schwere | SK | Stufe | Aktion | Tabellen | SAP | Status | Testdaten |
|---|---|---|---|---|---|---|---|---|---|---|
| CROSS-DUP-001 | Kunde = Lieferant (gleiche USt-ID oder IBAN) | duplicate | medium | 2 | B | review | business_partner, bp_tax_id, bp_bank_account | XD02/XK02 Verrechnung | draft | Defekt |
| CROSS-LEA-001 | Aufrechnungspotenzial: offene Forderung und Verbindlichkeit beim selben Partner | leakage | medium | 3 | C | process | fi_item | F-32/F-44 | draft | ohne Testfall |

## Offene fachliche Fragen (Victor)

- Definition "aktiver Debitor" für AR-COM-004: Umsatz in 12 Monaten oder OP > 0?
- Schwelle für AR-CON-001 (70 % abweichend) – oder ab 5 Belegen absolut?
- Policy-Defaults für HYG-Regeln je Kunde konfigurierbar – Standardwert? Abgegrenzt sind die Regeln über
  das Postenfenster des Laufs: AR-HYG-001/AP-HYG-001 verlangen `ERDAT` vor Fensterbeginn **und** keinen
  Posten im Fenster, AR-HYG-002 `ERDAT` im Fenster, älter als 12 Monate, ohne Posten. Damit überschneiden
  sich die beiden Regeln nicht mehr (2026-08-30).
- AP-LEA-001 Version 1.1: Kreditoren-Dubletten-Cluster einbeziehen (Doppelzahlung über zwei Konten).
