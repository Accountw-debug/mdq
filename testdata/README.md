# Testdaten

## Demo-Mandant (`demo_mandant/`)

Synthetischer SAP-ECC-Datensatz im SE16N-Exportformat (Tab, UTF-8, technische Spaltennamen,
Datum `YYYYMMDD`, Beträge deutsch mit Vorzeichen in `SHKZG`), erzeugt mit festem Seed:

```
uv run mdq demo generate --out testdata/demo_mandant          # Seed 20260830
uv run mdq load --input testdata/demo_mandant                 # 15 Tabellen, 0 Rejects
```

15 Dateien: KNA1 KNB1 KNBK KNVP KNB5 LFA1 LFB1 LFBK TIBAN BSID BSAD BSIK BSAK T052 T052U,
dazu `manifest.json` mit Seed, Generator-Version, Datenstand sowie Zeilen und sha256 je Datei.

| Kennzahl | Wert |
|---|---|
| Mandant / Buchungskreise | 100 / 1000 und 2000, Hauswährung EUR (V1 kennt eine Währung, D-030) |
| Debitoren / Kreditoren | 2.000 / 1.500, davon je ~8 % CpD (`XCPDK = X`) |
| Postenfenster | 2024-09-01 bis 2026-08-28; der Datenstand **ist** das Fensterende |
| Debitoren- / Kreditorenposten | ~40.000 / ~20.000, rund zwei Drittel der Rechnungen ausgeglichen |
| Zeilen gesamt | ~78.000, zusammen rund 11 MB |

**Stand: Basis-Mandant ohne Defekte.** Aufgabe 1 aus `docs/specs/SPRINT-2.md` erzeugt einen
bewusst *sauberen* Mandanten – auf ihm darf keine Regel aus `logic/rules/CATALOG.md` greifen.
Das ist keine Nebensache, sondern die Voraussetzung der Regression: jedes Finding muss später
genau einem Defekt zuzuordnen sein. `engine/tests/test_demo_base.py` prüft die Invarianten
dafür (eindeutige Kernnamen, USt-IdNr. und IBAN, gesetzte Zahlungsbedingung, `REPRF`, keine
Löschvormerkung, kein Belegpaar im Muster von AP-LEA-001, Skontoverlust unter der Meldegrenze).

**Die eingebauten Fehler kommen in Aufgabe 2** aus `demo_mandant/defects.yaml` obendrauf –
Dubletten mit Schreibvarianten, Zentralregulierer (darf NICHT als Dublette gelten), CpD-Konten
(dürfen NICHT geprüft werden), USt-IdNr. mit falschem Präfix oder Format, IBAN mit falscher
Prüfziffer, Löschvormerkung mit offenen Posten, fehlende Zahlungsbedingung, Löschkandidaten,
Doppelzahlungen mit Referenzvarianten (eine davon genettet → KEIN Finding), Skontoverluste,
Kunde = Lieferant, gleiche IBAN bei zwei Kreditoren.

Keine echten Firmen, Personen, IBAN oder USt-IdNr.: Namen entstehen kombinatorisch, die
Bankleitzahlen stammen aus einem in Deutschland nicht vergebenen Bereich, IBAN-Prüfziffern sind
gültig (schwifty), die DE-USt-IdNr. tragen eine gültige Prüfziffer (python-stdnum). Die Zuordnung
PLZ ↔ Ort ist plausibel, aber kein geprüftes Verzeichnis – V1 prüft nur das PLZ-Format.

## Encoding-Samples (`encoding_samples/`)

Fünf hässliche Varianten derselben KNA1-Zeilen. Der Loader muss alle identisch einlesen:

| Datei | Encoding | Trenner | Besonderheit |
|---|---|---|---|
| `KNA1_utf8_tab.txt` | UTF-8 | Tab | Referenz |
| `KNA1_cp1252_semicolon.txt` | Windows-1252 | ; | Umlaute in CP1252, CRLF |
| `KNA1_utf16_tab.txt` | UTF-16 LE mit BOM | Tab | SAP "unkonvertiert" |
| `KNA1_utf8bom_tab_quoted.txt` | UTF-8 mit BOM | Tab | Felder in Anführungszeichen |
| `BSID_formats.txt` | UTF-8 | Tab | Betrag `1.234,56`, `1234.56`, nachgestelltes Minus `1.234,56-`, Datum `20260830` und `30.08.2026` |

**`BSID_formats.txt` ist kein realistischer Export.** Ein echter SE16N-Export verwendet in der ganzen
Datei dieselbe Dezimaldarstellung (SAP-Benutzereinstellung SU3); hier stehen deutsche und ISO-Schreibweise
bewusst in derselben Spalte, damit `parse_amount` auf Wert-Ebene beide Formen beherrscht. Die Erkennung der
Notation je Datei kommt in Sprint 3 (D-035).

## Erwartete Findings (`expected/`)

`expected_findings.yaml`: Liste `{rule_id, bp_key, company_code?, document_no?}` –
der Regressionstest vergleicht exakt (nicht mehr, nicht weniger).
**Diese Datei wird nie an den Code angepasst** (CLAUDE.md Regel 1).
