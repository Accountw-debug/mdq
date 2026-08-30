# Testdaten

## Demo-Mandant (`demo_mandant/`, wird in Sprint 2 generiert)

Synthetischer SAP-ECC-Datensatz im SE16N-Exportformat (Tab, UTF-8, technische Spaltennamen):
KNA1 KNB1 KNBK TIBAN KNVP LFA1 LFB1 LFBK BSID BSAD BSIK BSAK T052 T052U.

Größe: ~2.000 Debitoren, ~1.500 Kreditoren, ~60.000 Posten über 24 Monate, 2 Buchungskreise
(1000, 2000). Erzeugt mit festem Seed (deterministisch).

**Eingebaute Fehler** (jeder erzeugt genau die Findings in `expected/`): Dubletten mit
Schreibvarianten (Umlaute, Rechtsform, Straße/Str.), Zentralregulierer (darf NICHT als
Dublette gelten), CpD-Konten (dürfen NICHT geprüft werden), USt-IDs mit falschem Präfix /
falschem Format, IBANs mit falscher Prüfziffer, Löschvormerkung mit offenen Posten,
Zahlungsbedingung leer, Debitoren ohne Umsatz seit 30 Monaten, Doppelzahlungen mit
Referenzvarianten (davon eine genettet durch Gutschrift → KEIN Finding), Skontoverluste,
Kunde = Lieferant mit gleicher USt-ID, gleiche IBAN bei zwei Kreditoren.

Keine echten Firmen, Personen, IBANs (nur Test-IBANs mit gültiger Prüfziffer) oder USt-IDs.

## Encoding-Samples (`encoding_samples/`)

Fünf hässliche Varianten derselben KNA1-Zeilen. Der Loader muss alle identisch einlesen:

| Datei | Encoding | Trenner | Besonderheit |
|---|---|---|---|
| `KNA1_utf8_tab.txt` | UTF-8 | Tab | Referenz |
| `KNA1_cp1252_semicolon.txt` | Windows-1252 | ; | Umlaute in CP1252, CRLF |
| `KNA1_utf16_tab.txt` | UTF-16 LE mit BOM | Tab | SAP "unkonvertiert" |
| `KNA1_utf8bom_tab_quoted.txt` | UTF-8 mit BOM | Tab | Felder in Anführungszeichen |
| `BSID_formats.txt` | UTF-8 | Tab | Betrag `1.234,56`, `1234.56`, nachgestelltes Minus `1.234,56-`, Datum `20260830` und `30.08.2026` |

## Erwartete Findings (`expected/`)

`expected_findings.yaml`: Liste `{rule_id, bp_key, company_code?, document_no?}` –
der Regressionstest vergleicht exakt (nicht mehr, nicht weniger).
**Diese Datei wird nie an den Code angepasst** (CLAUDE.md Regel 1).
