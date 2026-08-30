# Testdaten

## Demo-Mandant (`demo_mandant/`)

Synthetischer SAP-ECC-Datensatz im SE16N-Exportformat (Tab, UTF-8, technische Spaltennamen,
Datum `YYYYMMDD`, Beträge deutsch mit Vorzeichen in `SHKZG`), erzeugt mit festem Seed:

```
uv run mdq demo generate --out testdata/demo_mandant          # Seed 20260830, mit Defekten
uv run mdq demo generate --out /tmp/basis --no-defects        # reiner Basis-Mandant
uv run mdq demo expected                                      # erwartete Findings neu ableiten
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
| Zeilen gesamt | ~77.000, zusammen rund 12 MB |
| Eingebaute Fehler | 159 Defekte aus `demo_mandant/defects.yaml` → 230 erwartete Findings über 19 Regeln |

### Zwei Schichten

Der Generator baut zuerst einen bewusst **sauberen** Basis-Mandanten: auf ihm darf keine Regel
aus `logic/rules/CATALOG.md` greifen. Das ist keine Nebensache, sondern die Voraussetzung der
Regression – jedes Finding muss genau einem Defekt zuzuordnen sein (D-045).
`engine/tests/test_demo_base.py` prüft die Invarianten dafür (eindeutige Kernnamen, USt-IdNr.
und IBAN, gesetzte Zahlungsbedingung, `REPRF`, keine Löschvormerkung, kein Belegpaar im Muster
von AP-LEA-001, Skontoverlust unter der Meldegrenze) und arbeitet dazu auf einem eigens ohne
Defekte erzeugten Mandanten.

Darauf legt `demo_mandant/defects.yaml` die **eingebauten Fehler**: Dubletten mit
Schreibvarianten, Zentralregulierer (darf NICHT als Dublette gelten), CpD-Konten (dürfen NICHT
geprüft werden), USt-IdNr. mit falschem Präfix oder Format, IBAN mit falscher Prüfziffer,
Löschvormerkung mit offenen Posten, fehlende Zahlungsbedingung, Löschkandidaten,
Doppelzahlungen mit Referenzvarianten (drei davon genettet → KEIN Finding), Skontoverluste,
Kunde = Lieferant, gleiche IBAN bei zwei Kreditoren. `engine/tests/test_demo_defects.py` prüft
die Zahl der Fälle je Regel gegen den Katalog in `docs/specs/SPRINT-2.md` und jeden Ankerwert
einzeln.

Die Defekte nennen konkrete Kontonummern und gelten deshalb für Seed 20260830 (`seed:` in der
Datei). Ein Lauf mit anderem Seed bricht ab und verweist auf `--no-defects` (D-059).

### Einen Defekt ergänzen

1. **Typ wählen.** `uv run python -c "from mdq.demo.defects import defect_types; print(defect_types())"`
   zeigt die 18 vorhandenen Typen. Passt keiner, ist das eine Aufgabe an Claude Code: neuer
   Typ = eine kleine Funktion in `engine/mdq/demo/defects.py` mit `@defect_type("name")` und
   einem Docstring, der den Defekt in einem Satz erklärt.
2. **Zielkonto suchen.** Ein Konto, das noch keinen Defekt trägt – die belegten Konten stehen
   in `defects.yaml`. Passt das Konto nicht zum Typ (kein Bankkonto, keine offenen Posten),
   sagt der Generator es beim Erzeugen mit Kontonummer und Grund.
3. **Eintrag anhängen** – ans Ende von `defects.yaml`, mit fortlaufender `id`:

   ```yaml
     - id: DEF-0160
       type: iban_checksum
       note: "Ein Satz, warum das fachlich ein Fehler ist."
       params:
         bp_keys: ["V:0000200123"]
       expected:
         - { rule_id: AP-VAL-003 }
   ```

   `expected` ohne `bp_key` wird über alle Treffer des Defekts ausgerollt. Ein Negativfall
   trägt ausdrücklich `expected: []`. Braucht der Defekt ein Konto, das schon belegt ist,
   kommt `overlaps: [DEF-0007]` dazu – sonst bricht der Lauf ab (D-061).
4. **Erzeugen und prüfen.**

   ```
   uv run mdq demo generate --out testdata/demo_mandant
   uv run mdq demo expected
   uv run pytest
   ```

   Die Zahl der erwarteten Findings je Regel steht in `engine/tests/test_demo_defects.py`
   (`FINDINGS_PER_RULE`) und in `docs/specs/SPRINT-2.md`. Ändert sich eine Zahl, gehört sie
   an **beiden** Stellen angepasst – bewusst, nicht nebenbei.

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

`expected_findings.yaml`: Liste `{rule_id, bp_key, company_code?, document_no?, finding_key?,
from_rule_version?, defect}` – der Regressionstest vergleicht exakt (nicht mehr, nicht weniger).

**Die Datei wird generiert** (`uv run mdq demo expected`) und nie von Hand gepflegt: Änderungen
gehören in `demo_mandant/defects.yaml`. Jede Zeile nennt den Defekt, aus dem sie stammt.
`from_rule_version` heisst: dieses Finding ist erst ab der genannten Regelversion Pflicht – bis
dahin weist die Regression es als bekannt-offen aus (D-054). Betroffen sind die beiden
Doppelzahlungen über zwei Kreditorenkonten, die AP-LEA-001 erst in Version 1.1 findet.

**Erwartete Ergebnisse werden nie an den Code angepasst** (CLAUDE.md Regel 1).
