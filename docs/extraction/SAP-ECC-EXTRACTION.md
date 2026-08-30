# Extraktionsanleitung SAP ECC – Finance Master Data & Leakage Check

Ziel: 5–6 Exports je Seite (Debitoren/Kreditoren), Aufwand beim Kunden ca. 1–2 Stunden
für einen SAP-Key-User. Es wird nichts im System geändert, nur gelesen.

## Grundeinstellungen für alle Exports (SE16N)

1. Transaktion **SE16N**, Tabelle eingeben, **Max. Anzahl Treffer leeren** (sonst 500 Zeilen).
2. Layout: **technische Feldnamen** anzeigen (Spaltenüberschriften müssen z. B. `KUNNR`, nicht "Debitor" lauten).
3. Nur die gelisteten Felder ausgeben (Feldauswahl im Layout) – weniger ist mehr.
4. Export: **Liste → Exportieren → Lokale Datei → "Tabulatorgetrennt" oder "unkonvertiert"**.
   Encoding UTF-8, wenn wählbar. Andere Formate (Excel, CP1252) werden erkannt, sind aber langsamer.
5. Dateiname = Tabellenname (`KNA1.txt`, `BSID.txt`, …). Mehrere Mandanten/Buchungskreise: je Datei einen Zusatz (`BSID_1000.txt`).
6. Führende Nullen dürfen **nicht** entfernt werden (Excel schneidet sie ab – deshalb Textdatei).

## Minimal-Set V1

### Debitoren (AR)

| Tabelle | Inhalt | Felder (technisch) | Filter |
|---|---|---|---|
| KNA1 | Allgemeine Daten | KUNNR LAND1 NAME1 NAME2 NAME3 NAME4 SORTL ORT01 PSTLZ REGIO STRAS PFACH PSTL2 ADRNR KTOKD XCPDK LOEVM SPERR KNRZA KONZS SPRAS ERDAT ERNAM TELF1 STCD1 STCD2 STCEG | keiner |
| KNB1 | Buchungskreisdaten | KUNNR BUKRS AKONT ZTERM MAHNA SPERR LOEVM ZWELS ZAHLS KNRZB TOGRU ZUAWA ERDAT ERNAM | BUKRS im Scope |
| KNBK | Bankverbindungen | KUNNR BANKS BANKL BANKN BKONT BVTYP KOINH XEZER | keiner |
| TIBAN | IBAN zu Bankverbindung | BANKS BANKL BANKN BKONT IBAN VALID_FROM | keiner (Tabelle ist klein) |
| KNVP | Partnerrollen (Regulierer, Rechnungsempfänger) | KUNNR VKORG VTWEG SPART PARVW KUNN2 PARZA | PARVW in RG RE AG WE |
| BSID + BSAD *oder* FBL5N | Offene und ausgeglichene Posten | KUNNR BUKRS GJAHR BELNR BUZEI BUDAT BLDAT CPUDT BLART BSCHL SHKZG UMSKZ WAERS WRBTR DMBTR XBLNR ZUONR SGTXT ZFBDT ZTERM ZBD1T ZBD1P SKFBT SKNTO ZLSCH ZLSPR REBZG HKONT AUGDT AUGBL | BUDAT letzte 24 Monate; BSID komplett |
| T052 (+ T052U) | Zahlungsbedingungen | ZTERM ZTAGG ZTAG1 ZPRZ1 ZTAG2 ZPRZ2 ZTAG3 · T052U: ZTERM SPRAS TEXT1 | keiner |

### Kreditoren (AP)

| Tabelle | Inhalt | Felder (technisch) | Filter |
|---|---|---|---|
| LFA1 | Allgemeine Daten | LIFNR LAND1 NAME1 NAME2 NAME3 NAME4 SORTL ORT01 PSTLZ REGIO STRAS PFACH PSTL2 ADRNR KTOKK XCPDK LOEVM SPERR LNRZA KONZS SPRAS ERDAT ERNAM TELF1 STCD1 STCD2 STCEG | keiner |
| LFB1 | Buchungskreisdaten | LIFNR BUKRS AKONT ZTERM SPERR LOEVM ZWELS ZAHLS LNRZB TOGRU **REPRF** ZUAWA ERDAT ERNAM | BUKRS im Scope |
| LFBK | Bankverbindungen | LIFNR BANKS BANKL BANKN BKONT BVTYP KOINH XEZER | keiner |
| TIBAN | wie oben | – | – |
| BSIK + BSAK *oder* FBL1N | Posten | wie BSID/BSAD mit LIFNR statt KUNNR, zusätzlich EBELN | BUDAT letzte 24 Monate |
| T052 | wie oben | – | – |

## Alternative: FBL5N / FBL1N statt BSID/BSAD bzw. BSIK/BSAK

Wenn SE16N für Postentabellen zu groß ist: **FBL5N** (Debitoren) bzw. **FBL1N** (Kreditoren),
Auswahl "Alle Posten", Buchungsdatum letzte 24 Monate, Layout mit den oben genannten
Feldern, Export als Tabellenkalkulation/Textdatei. Wichtig: Spalte **Ausgleichsbeleg** und
**Ausgleichsdatum** ins Layout nehmen, sonst ist offen/ausgeglichen nicht erkennbar.

## Erweiterung (nur wenn vereinbart)

| Tabelle | Zweck | Felder |
|---|---|---|
| KNB5 | Mahndaten | KUNNR BUKRS MABER MAHNS MADAT MANSP KNRMA |
| KNVV | Vertriebsbereich | KUNNR VKORG VTWEG SPART ZTERM INCO1 WAERS KDGRP AUFSD LIFSD FAKSD LOEVM |
| ADR6 | E-Mail-Adressen | ADDRNUMBER SMTP_ADDR FLGDEFAULT |
| CDHDR + CDPOS | Änderungsbelege (Bankdaten, Sperren) | CDHDR: OBJECTCLAS OBJECTID CHANGENR USERNAME UDATE UTIME TCODE · CDPOS: OBJECTCLAS OBJECTID CHANGENR TABNAME FNAME VALUE_OLD VALUE_NEW CHNGIND · Filter OBJECTCLAS = DEBI / KRED, UDATE letzte 24 Monate |
| REGUH + REGUP | Zahlläufe (erfolgreiche Zahlungen an IBAN) | REGUH: LAUFD LAUFI ZBUKR LIFNR KUNNR VBLNR ZALDT RWBTR WAERS ZBNKS ZBNKL ZBNKN ZIBAN · REGUP: LAUFD LAUFI VBLNR BELNR GJAHR |
| FEBKO + FEBEP | Kontoauszüge (Zahler-IBAN) | FEBKO: KUKEY AZDAT ABSND · FEBEP: KUKEY ESNUM KWBTR KWAER PABLN PARTN VGEXT SGTXT |

## Kontrollsummen (bitte mitliefern)

- Saldenliste Debitoren/Kreditoren je Buchungskreis zum Stichtag (S_ALR_87012172 / S_ALR_87012082 oder FBL5N/FBL1N Summenzeile)
- Anzahl Debitoren/Kreditoren je Kontengruppe (SE16N KNA1/LFA1 mit Summenfunktion)

Damit prüft das Tool, dass alle Posten angekommen sind, bevor es Findings meldet.

## Datenschutz

Debitoren können Privatpersonen enthalten. Der Export bleibt beim Kunden bzw. auf dem
vereinbarten System; die Auswertung läuft lokal, es findet keine Übertragung an Dritte statt
(VIES-Abfragen nur mit ausdrücklicher Freigabe).
