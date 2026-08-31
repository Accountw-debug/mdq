# Extraktionsanleitung SAP ECC – Finance Master Data & Leakage Check

Ziel: **15 Exportdateien** – vier für beide Seiten gemeinsam, sechs Debitoren, fünf
Kreditoren. Aufwand beim Kunden ca. 1–2 Stunden für einen SAP-Key-User. Es wird nichts im
System geändert, nur gelesen.

## Grundeinstellungen für alle Exports (SE16N)

1. Transaktion **SE16N**, Tabelle eingeben, **Max. Anzahl Treffer leeren** (sonst 500 Zeilen).
2. Layout: **technische Feldnamen** anzeigen (Spaltenüberschriften müssen z. B. `KUNNR`, nicht "Debitor" lauten).
3. Nur die gelisteten Felder ausgeben (Feldauswahl im Layout) – weniger ist mehr.
4. Export: **Liste → Exportieren → Lokale Datei → "Tabulatorgetrennt" oder "unkonvertiert"**.
   Encoding UTF-8, wenn wählbar. Andere Formate (Excel, CP1252) werden erkannt, sind aber langsamer.
5. Dateiname = Tabellenname (`KNA1.txt`, `BSID.txt`, …). Mehrere Mandanten/Buchungskreise: je Datei einen Zusatz (`BSID_1000.txt`).
6. Führende Nullen dürfen **nicht** entfernt werden (Excel schneidet sie ab – deshalb Textdatei).

## Minimal-Set V1

Die Feldlisten stehen so in `logic/mappings/sap_ecc.yaml` – der Datei, die die Engine
wirklich liest. Eine Spalte, die im Export fehlt, meldet der Lauf mit Namen; eine Spalte,
die weder abgebildet noch ausdrücklich ignoriert ist, bricht ihn ab (Regel 4). Dass diese
Anleitung und das Mapping nicht auseinanderlaufen, hält ein Test fest
(`engine/tests/test_extraction_doc.py`).

### Beide Seiten (Pflicht)

| Tabelle | Inhalt | Felder (technisch) | Filter |
|---|---|---|---|
| T001 | Buchungskreise mit **Hauswährung** | BUKRS BUTXT WAERS LAND1 | BUKRS im Scope |
| TIBAN | IBAN zu Bankverbindung | BANKS BANKL BANKN BKONT IBAN VALID_FROM | keiner (Tabelle ist klein) |
| T052 | Zahlungsbedingungen: Skontotage und -prozent | ZTERM ZTAGG ZTAG1 ZPRZ1 ZTAG2 ZPRZ2 ZTAG3 | keiner |
| T052U | Texte zu den Zahlungsbedingungen | ZTERM SPRAS TEXT1 | SPRAS = D bevorzugt |

Ohne T001 gibt es keine Hauswährung, und `DMBTR` wäre ein Betrag ohne Währung. Die
Relevanzstufe bricht dann ab und nennt die fehlende Tabelle – ein Ersatz über die
Belegwährung (`WAERS` in BSID/BSIK) wäre bei jeder Fremdwährungsrechnung falsch.
Kommen im Scope mehrere Hauswährungen vor, endet der Lauf mit Exit 2 und nennt den
Ausweg: je Hauswährung einen Lauf, abgegrenzt über `--company-codes`.

TIBAN, T052 und T052U werden **einmal** exportiert und gelten für beide Seiten.

### Debitoren (AR)

| Tabelle | Inhalt | Felder (technisch) | Filter |
|---|---|---|---|
| KNA1 | Allgemeine Daten | KUNNR LAND1 NAME1 NAME2 NAME3 NAME4 SORTL ORT01 PSTLZ REGIO STRAS PFACH PSTL2 ADRNR KTOKD XCPDK LOEVM SPERR KNRZA KONZS SPRAS ERDAT ERNAM TELF1 STCD1 STCD2 STCEG | keiner |
| KNB1 | Buchungskreisdaten | KUNNR BUKRS AKONT ZTERM MAHNA SPERR LOEVM ZWELS ZAHLS KNRZB TOGRU ZUAWA ERDAT ERNAM | BUKRS im Scope |
| KNBK | Bankverbindungen | KUNNR BANKS BANKL BANKN BKONT BVTYP KOINH XEZER | keiner |
| KNVP | Partnerrollen (Regulierer, Rechnungsempfänger) | KUNNR VKORG VTWEG SPART PARVW KUNN2 PARZA | PARVW in RG RE AG WE |
| BSID | Offene Posten | KUNNR BUKRS GJAHR BELNR BUZEI BUDAT BLDAT CPUDT BLART BSCHL SHKZG UMSKZ WAERS WRBTR DMBTR XBLNR ZUONR SGTXT ZFBDT ZTERM ZBD1T ZBD1P SKFBT SKNTO ZLSCH ZLSPR REBZG HKONT AUGDT AUGBL | komplett |
| BSAD | Ausgeglichene Posten | KUNNR BUKRS GJAHR BELNR BUZEI BUDAT BLDAT CPUDT BLART BSCHL SHKZG UMSKZ WAERS WRBTR DMBTR XBLNR ZUONR SGTXT ZFBDT ZTERM ZBD1T ZBD1P SKFBT SKNTO ZLSCH ZLSPR REBZG HKONT AUGDT AUGBL | BUDAT letzte 24 Monate |

### Kreditoren (AP)

| Tabelle | Inhalt | Felder (technisch) | Filter |
|---|---|---|---|
| LFA1 | Allgemeine Daten | LIFNR LAND1 NAME1 NAME2 NAME3 NAME4 SORTL ORT01 PSTLZ REGIO STRAS PFACH PSTL2 ADRNR KTOKK XCPDK LOEVM SPERR LNRZA KONZS SPRAS ERDAT ERNAM TELF1 STCD1 STCD2 STCEG | keiner |
| LFB1 | Buchungskreisdaten | LIFNR BUKRS AKONT ZTERM SPERR LOEVM ZWELS ZAHLS LNRZB TOGRU REPRF ZUAWA ERDAT ERNAM | BUKRS im Scope |
| LFBK | Bankverbindungen | LIFNR BANKS BANKL BANKN BKONT BVTYP KOINH XEZER | keiner |
| BSIK | Offene Posten | LIFNR BUKRS GJAHR BELNR BUZEI BUDAT BLDAT CPUDT BLART BSCHL SHKZG UMSKZ WAERS WRBTR DMBTR XBLNR ZUONR SGTXT ZFBDT ZTERM ZBD1T ZBD1P SKFBT SKNTO ZLSCH ZLSPR REBZG EBELN HKONT AUGDT AUGBL | komplett |
| BSAK | Ausgeglichene Posten | LIFNR BUKRS GJAHR BELNR BUZEI BUDAT BLDAT CPUDT BLART BSCHL SHKZG UMSKZ WAERS WRBTR DMBTR XBLNR ZUONR SGTXT ZFBDT ZTERM ZBD1T ZBD1P SKFBT SKNTO ZLSCH ZLSPR REBZG EBELN HKONT AUGDT AUGBL | BUDAT letzte 24 Monate |

Die vier Postentabellen sind bis auf drei Dinge gleich: Kontonummernfeld (`KUNNR` bzw.
`LIFNR`), Bestellnummer (`EBELN`, nur auf der Kreditorenseite) und die Frage, ob der
Posten offen ist – das sagt schon die Quelltabelle, ein eigenes Feld gibt es dafür nicht.
`AUGDT` und `AUGBL` gehören trotzdem in **jeden** der vier Exports: ohne sie ist nicht
erkennbar, wann und womit ausgeglichen wurde.

Zwei Felder werden erfahrungsgemäß übersehen und sind beide wichtig: **REPRF** in LFB1
(Prüfung auf doppelte Rechnung – ohne das Feld fehlt die Ursache zu jeder Doppelzahlung)
und **XBLNR** in den Postentabellen (Referenz, meist die Rechnungsnummer des Lieferanten –
ohne sie ist eine Doppelzahlung nicht als solche zu erkennen).

## Alternative: FBL5N / FBL1N statt BSID/BSAD bzw. BSIK/BSAK

Wenn SE16N für Postentabellen zu groß ist: **FBL5N** (Debitoren) bzw. **FBL1N** (Kreditoren),
Auswahl "Alle Posten", Buchungsdatum letzte 24 Monate, Layout mit den oben genannten
Feldern, Export als Tabellenkalkulation/Textdatei. Wichtig: Spalte **Ausgleichsbeleg** und
**Ausgleichsdatum** ins Layout nehmen, sonst ist offen/ausgeglichen nicht erkennbar.

## Erweiterung (nur wenn vereinbart)

Diese Tabellen liest V1 noch nicht; im Mapping stehen sie mit `status: later` und ihren
Feldern von Interesse. Wer sie mitliefert, spart einen zweiten Termin.

| Tabelle | Zweck | Felder |
|---|---|---|
| KNB5 | Mahndaten | KUNNR BUKRS MABER MAHNS MADAT MANSP KNRMA |
| KNVV | Vertriebsbereich | KUNNR VKORG VTWEG SPART ZTERM INCO1 INCO2 WAERS KDGRP AUFSD LIFSD FAKSD LOEVM |
| ADR6 | E-Mail-Adressen | ADDRNUMBER SMTP_ADDR |
| CDHDR | Änderungsbelege, Kopf | OBJECTCLAS OBJECTID CHANGENR USERNAME UDATE UTIME TCODE |
| CDPOS | Änderungsbelege, Positionen | OBJECTCLAS OBJECTID CHANGENR TABNAME FNAME VALUE_NEW VALUE_OLD CHNGIND |

Filter für CDHDR/CDPOS: `OBJECTCLAS` in DEBI / KRED, `UDATE` letzte 24 Monate.

Ohne Eintrag im Mapping und deshalb ohne Feldliste hier – erst wenn eine Regel sie
braucht: REGUH + REGUP (Zahlläufe, erfolgreiche Zahlungen an eine IBAN) und
FEBKO + FEBEP (Kontoauszüge, Zahler-IBAN).

## Kontrollsummen (bitte mitliefern)

- Saldenliste Debitoren/Kreditoren je Buchungskreis zum Stichtag (S_ALR_87012172 / S_ALR_87012082 oder FBL5N/FBL1N Summenzeile)
- Anzahl Debitoren/Kreditoren je Kontengruppe (SE16N KNA1/LFA1 mit Summenfunktion)

Damit prüft das Tool, dass alle Posten angekommen sind, bevor es Findings meldet.

## Datenschutz

Debitoren können Privatpersonen enthalten. Der Export bleibt beim Kunden bzw. auf dem
vereinbarten System; die Auswertung läuft lokal, es findet keine Übertragung an Dritte statt
(VIES-Abfragen nur mit ausdrücklicher Freigabe).
