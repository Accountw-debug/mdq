# Sprint 2 – Demo-Mandant: synthetischer SAP-ECC-Datensatz + erwartete Findings

Ziel: Ein deterministisch erzeugter, realistischer SAP-ECC-Datensatz im SE16N-Exportformat
mit **bewusst eingebauten Fehlern**, und eine Liste der Findings, die daraus entstehen müssen.
Das ist die Wahrheit, gegen die ab Sprint 3 jede Regel geprüft wird (Regression).

Grundidee: **Fehler sind Daten, nicht Code.** Der Generator erzeugt einen sauberen Basis-
Mandanten und wendet danach eine Liste von Defekten aus `testdata/demo_mandant/defects.yaml`
an. Jeder Defekt trägt die Findings, die er erzeugen muss – oder ausdrücklich `expected: []`,
wenn er ein Negativfall ist (darf **kein** Finding erzeugen). Die erwartete Findings-Liste
wird aus den Defekten abgeleitet, nicht von Hand gepflegt. Victor ergänzt später Defekte
(für seine 24 Findings), ohne den Generator anzufassen.

## Umfang des Mandanten

- Mandant 100, Buchungskreise 1000 und 2000, Hauswährung EUR in beiden (V1 kennt eine Währung, D-030).
- ~2.000 Debitoren, ~1.500 Kreditoren, je ca. 8 % CpD-Konten (`XCPDK = X`), Kontengruppen DEBI/KUNA bzw. KRED/LIEF.
- Posten über 24 Monate (2024-09-01 bis 2026-08-28 = Datenstand): ~40.000 Debitoren-, ~20.000 Kreditorenposten.
  Rechnungen (BLART DR bzw. KR), Zahlungen (DZ/KZ), Gutschriften (DG/KG). ~65 % ausgeglichen (BSAD/BSAK), Rest offen (BSID/BSIK).
  Zahlverhalten realistisch: Skontonutzung bei ~40 % der Rechnungen mit Skontobedingung, Verzögerungen normalverteilt.
- Zahlungsbedingungen T052: ZB00 (sofort), ZB01 (10 Tage 3 %, 30 netto), ZB02 (14 Tage 2 %, 30 netto), ZB03 (30 netto), ZB04 (60 netto); T052U mit deutschen Texten.
- Partnerrollen KNVP für alle Debitoren (AG = selbst), dazu 30 Zentralregulierer-Konstellationen (RG ≠ AG) – **Negativfälle** für Dubletten.
- Bankverbindungen: 85 % der Debitoren, 98 % der Kreditoren; IBANs mit gültiger Prüfziffer über schwifty, **erfundene** Bankleitzahlen, keine Bank-Existenzprüfung.
- USt-IDs: Formate laut `logic/dictionaries/vat_id_patterns.yaml`, DE-Prüfziffer über python-stdnum gültig; ~75 % Deutschland, Rest AT/NL/FR/IT/PL/CH/US.
- Namen: **erfunden** durch Kombinatorik (Silbenlisten + Branchenwort + Rechtsform aus `legal_forms.yaml`). Keine echten Firmen, Personen oder Marken. Städte/PLZ aus einer eingebetteten Liste von ~200 deutschen und ~50 europäischen Orten (öffentliche Daten).
- Dateien im SE16N-Format: Tab, UTF-8, technische Spaltennamen, Datum YYYYMMDD, Betrag deutsch (`1.234,56`, Vorzeichen über SHKZG, **nicht** nachgestellt), Schlüssel mit führenden Nullen:
  `KNA1 KNB1 KNBK TIBAN KNVP KNB5 LFA1 LFB1 LFBK BSID BSAD BSIK BSAK T052 T052U` → `testdata/demo_mandant/<TABELLE>.txt`.
- `manifest.json`: Seed, Generator-Version, Zeilen und sha256 je Datei, Datenstand.

## Ankerfälle – die sechs Beispiel-Findings müssen wörtlich wahr werden

Die Entitäten aus `logic/examples/findings/` werden mit exakt diesen Werten gesetzt:

| bp_key | Name | Werte |
|---|---|---|
| C:0000100234 | Müller Maschinenbau GmbH, Robert-Bosch-Str. 12, 86159 Augsburg | STCEG `AT U12345678`, OP 45.210,00 in 1000, 27 Zahlungen, letzte 12.08.2026, Volumen 12M 312.400,00 |
| C:0000100987 | Mueller Maschinenbau GmbH, Robert Bosch Straße 12, 86159 Augsburg | STCEG `DE123456780` (formatgültig), 2 Zahlungen, 2 OP à 3.200,00, kein RG/RE-Bezug in KNVP |
| C:0000101502 | Hartmann Logistik e.K., Bremen | LOEVM zentral `X`, 3 OP in 1000 = 8.930,00, ältester 03.11.2025, Volumen 12M 8.930,00 (nur diese drei Rechnungen) |
| V:0000200845 | Stahlhandel Bergmann KG, Essen | zwei bezahlte KR-Rechnungen 32.000,00: 1900004411 (XBLNR `RE-4711`, 01.03.2026) und 1900004587 (`RE4711`, 10.03.2026), keine Gutschrift danach; Volumen 12M 1.284.000,00 |
| V:0000200117 | Elektro Brandt GmbH & Co. KG, Kassel | ZTERM ZB02 (14 Tage 2 %), 31 Rechnungen in 12M, davon 23 nach Skontofrist bezahlt, Skontobasis dieser 23 = 240.620,00; OP 18.400,00 (8 Rechnungen); Volumen 12M 259.020,00 |
| V:0000201330 | Nordwind Verpackungen GmbH, Lübeck | IBAN `DE44500105175407324932` (Prüfziffer ungültig), OP 27.300,00 in 2000, keine Zahlung an diese IBAN |

Damit sind F-001 bis F-006 die ersten sechs Einträge der erwarteten Findings.

## Defekt-Katalog (`defects.yaml`) – Pflichtinhalt V1

Jeder Eintrag: `id`, `type`, `params` (bp_keys, company_code, Werte), `expected: [{rule_id, bp_key, company_code?, finding_key?}]`, `note` (fachlich, ein Satz).

**Positivfälle (erzeugen Findings):**
- 12 Dubletten-Cluster Debitoren (Varianten: Umlaut/Transliteration, Rechtsform-Schreibweise, Str./Straße, Postfach vs. Straße, Name2-Verschiebung, Tippfehler Levenshtein 1), 8 Cluster Kreditoren → AR-DUP-001 / AP-DUP-001.
  **Zwei der zwölf Debitoren-Cluster tragen die Variante „Postfach vs. Straße"** (Victor, 2026-08-30): das eine Konto führt die Straßenadresse, das andere nur ein Postfach – ohne Adress-Normalisierung wird das Paar nicht gefunden.
- 15 USt-IDs mit falschem Präfix → AR-VAL-001 (davon 5 mit Dublette als Soll-Quelle), 10 → AP-VAL-001
- 12 USt-IDs mit ungültigem Format → AR-VAL-002 (7) / AP-VAL-002 (5).
  **Drei der sieben Debitorenfälle tragen die Variante „Steuernummer im USt-IdNr.-Feld"** (Victor, 2026-08-30):
  `STCEG` enthält eine deutsche Steuernummer im Format `123/456/78901` – der häufigste Formatfehler in der Praxis.
- 8 IBANs mit ungültiger Prüfziffer (5 Kreditoren, 3 Debitoren) → AP-VAL-003 / AR-VAL-003
- 6 Debitoren mit Löschvormerkung oder Sperre und offenen Posten (zentral und je Buchungskreis, einer in beiden Buchungskreisen → zwei Findings) → AR-CON-002
- 20 Debitoren ohne Zahlungsbedingung im Buchungskreis, davon 15 mit eindeutig meistgenutzter ZTERM auf Belegen → AR-COM-002
- 40 Debitoren mit `ERDAT` vor Fensterbeginn, ohne Posten im Fenster und ohne OP → AR-HYG-001; 25 Kreditoren ebenso → AP-HYG-001
- 10 Doppelzahlungspaare Kreditoren mit Referenzvarianten (Bindestrich, führende Null, Leerzeichen, Groß/klein), davon 2 über Kreditoren-Dubletten hinweg (für Version 1.1) → AP-LEA-001
- 8 Kreditoren mit Skontoverlust > 1.000,00 in 12M → AP-LEA-002
- 4 Kreditoren-Paare mit gleicher IBAN ohne Regulierer-Bezug → AP-CON-001
- 5 Kunde = Lieferant (gleiche USt-ID) → CROSS-DUP-001
- 30 Kreditoren ohne REPRF → AP-COM-003
- 10 Debitoren mit Platzhalter-Namen („Test", „unbekannt", „xxx") → AR-VAL-005
- 6 Akontozahlungen Debitoren ohne Rechnungsbezug, älter 30 Tage → AR-LEA-001

**Negativfälle (dürfen kein Finding erzeugen, `expected: []`):**
- 30 Zentralregulierer (gleiche IBAN/Adresse bei RG-Beziehung in KNVP)
- Alle CpD-Konten – auch wenn sie Dubletten-ähnliche Namen tragen (10 bewusst so gesetzt)
- 3 Doppelzahlungspaare, die durch Gutschrift innerhalb 180 Tagen genettet sind
- 5 Paare „gleicher Kernname, andere Rechtsform" (GmbH vs. AG) – höchstens Hinweis, nie Dublette
- 5 Debitoren mit Löschvormerkung **ohne** offene Posten
- 20 Debitoren mit korrekter Skontonutzung

Rechtliche Fußnote in der Datei: alle Werte erfunden; IBAN-Prüfziffern gültig, Banken nicht existent.

## Aufgaben (Plan → Freigabe → Umsetzung → Tests → Commit)

### 1. Generator-Gerüst und Basis-Mandant
- `engine/mdq/demo/` als Paket: `generate.py` (CLI `mdq demo generate --out testdata/demo_mandant --seed 20260830`), `base.py` (saubere Stammdaten), `postings.py` (Posten), `writers.py` (SE16N-Format, aus `logic/mappings/sap_ecc.yaml` die Spaltenlisten je Tabelle lesen – keine zweite Feldliste im Code), `names.py` (Kombinatorik, Wörterbuch-Rechtsformen), `geo.py` (Ortsliste).
- Determinismus: eigener `random.Random(seed)`, keine Set-Iteration ohne Sortierung, keine `datetime.now()`. Test: zwei Läufe → identische sha256 je Datei.
- Geld als `Decimal` mit `quantize(Decimal("0.01"))`; Summen ausgeglichener Belege stimmen (Zahlung = Rechnung − Skonto).
- Akzeptanz: `mdq load --input testdata/demo_mandant` → 15 Tabellen erkannt, 0 Rejects, Zeilen laut `manifest.json`.

### 2. Defekt-Schicht
- `defects.py`: liest `defects.yaml`, wendet Defekte in definierter Reihenfolge auf den Basis-Mandanten an. Jeder Defekttyp ist eine kleine Funktion mit Docstring, der den Defekt in einem Satz erklärt. Unbekannter Typ → Fehler.
- Ankerfälle als eigener Defekttyp `anchor` mit den Werten aus der Tabelle oben.
- `expected_findings.yaml` wird **generiert** aus `defects.yaml` (`mdq demo expected`), mit Kopfkommentar „generiert – Änderungen in defects.yaml".
- Test: Zahl der Positivfälle und Negativfälle wie im Katalog; jeder Ankerwert liegt exakt in den Dateien (OP-Summe 45.210,00 für C:0000100234 etc.).

### 3. Regelköpfe füllen und Katalog anbinden
- Die drei implementierten Regeln bekommen `tests.hits / no_hits / edge` mit echten bp_keys aus `defects.yaml` (Hinweise aus D-021 verschwinden für diese drei).
- Für jede Regel aus `CATALOG.md`, die in `defects.yaml` als `rule_id` vorkommt, prüft ein Test, dass die Regel-ID dort existiert – und umgekehrt: jede erwartete Regel im Katalog hat mindestens einen Defekt. Regeln ohne Defekt stehen im Katalog mit Vermerk „ohne Testfall".
- `testdata/README.md` aktualisieren: Zahlen, Tabellen, wie man einen Defekt ergänzt (Schritt-für-Schritt für Victor).

### 4. Regression vorbereiten (aktiv ab Sprint 3)
- `engine/tests/test_regression.py`: lädt den Demo-Mandanten, führt alle Regeln aus, vergleicht mit `expected_findings.yaml` exakt (nicht mehr, nicht weniger, gleiche finding_keys). In Sprint 2 ist der Test mit `pytest.mark.skip(reason="Mapping SAP → kanonisch ab Sprint 3 (D-068)")` markiert – **nicht** gelöscht, damit er sichtbar bleibt.
- Vergleich meldet Abweichungen als drei Listen: fehlend, unerwartet, abweichend – mit rule_id und bp_key, ohne Geschäftspartnerdaten.

## Victors Teil
- Zu jedem der 24 weiteren Findings einen Defekt-Eintrag in `defects.yaml` (Typ existiert schon oder wird als neuer Typ angemeldet → Aufgabe an Claude Code).
- Katalog: Status `spec` für die Regeln, die Sprint 3 zuerst baut (Vorschlag: AR-COM-002, AR-VAL-002, AR-VAL-003, AR-VAL-005, AR-HYG-001, AR-DUP-001, AP-VAL-001, AP-VAL-003, AP-CON-001, AP-COM-003, AP-HYG-001, AP-LEA-002, CROSS-DUP-001).

## Definition of Done Sprint 2
- Generator deterministisch, 15 Dateien, `mdq load` ohne Rejects, Ankerwerte exakt, Positiv-/Negativfälle vollständig, `expected_findings.yaml` generiert, drei Regelköpfe ohne D-021-Hinweis, Regressionstest angelegt (skip), README für Defekte geschrieben.
- Laufzeit der Generierung unter 60 Sekunden; Dateien zusammen unter 20 MB (werden eingecheckt – Test-Fixture, keine Kundendaten).
- DECISIONS und SESSION_LOG gepflegt.

## Nicht in Sprint 2
Mapping SAP → kanonisch, Staging, Notationserkennung (D-035), neue Regeln – alles Sprint 3.
Fremdwährungs-Buchungskreis (kommt als eigener kleiner Mandant `demo_mandant_chf/` in Sprint 3, um den D-030-Abbruch zu testen).
