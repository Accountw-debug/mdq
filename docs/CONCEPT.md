# MDQ – Produktkonzept (Stand 30.08.2026)

## 1. Zielbild

Ein Check für Finance-Stammdaten (Debitoren + Kreditoren) aus SAP ECC/S4, der pro Finding
liefert: **Ist, Soll, Quellen, Konfidenz-Stufe, Schadensklasse, Euro-Wirkung, SAP-Handlungsanweisung.**
Positionierung: kein MDM, sondern *Finance Master Data & Leakage Check* – Diagnose mit
konkreten Bereinigungslisten, Türöffner für Cash App (AR) und AP-Automatisierung.

Grundprinzip: **Logik und Code strikt trennen.** Regeln, Mappings, Wörterbücher und
Report-Templates sind Konfiguration (YAML + SQL auf kanonischem Schema). Die Engine ist
austauschbar; die Logik bleibt.

## 2. Das zentrale Objekt: Finding

Alles erzeugt oder konsumiert Findings. Schema: `logic/finding.schema.json`.
Ein Finding trägt immer: Regel + Version, Seite (AR/AP/CROSS), Kategorie, Schwere,
Schadensklasse, Stufe, Aktionstyp, Ist, Soll (optional), Evidenzen, €-Wirkung mit
offengelegter Rechnung, Warum, Wenn-falsch, SAP-Schritt, Status, Datenstand.

## 3. Funktionsblöcke

| Block | V1 (dieses Repo) | Später |
|---|---|---|
| 1 Intake | SE16N-/FBL-Exports, Auto-Erkennung, SAP-Formate, Mapping je Kunde, Datenprofil, Scoping (BUKRS, Zeitfenster, AR/AP) | S/4-OData, RFC, BC/DATEV |
| 2 BP-360 | Kanonischer Geschäftspartner mit Rollen, Adressen, Banken, Steuer-IDs, BUKRS-Daten; abgeleitet: Aktivität, Relevanzgewicht (OP + 12M-Volumen), Zahlverhalten, Zahler-Mapping | Konzernhierarchie |
| 3 Regelwerk | Katalog mit Schwere, Gewicht, Klartext, SAP-Aktion; Kategorien Vollständigkeit/Validität/Konsistenz/Hygiene/Risiko; „nicht geprüft"-Ausweis | Eigene Regeln per UI |
| 4 Dubletten | AR, AP, über Kreuz (Kunde = Lieferant); Cluster mit Match-Gründen; Ausschlüsse CpD/Regulierer; Review-Queue; Whitelist; Bereinigungsvorschlag mit Golden Record | Konzern-Cluster mit Registerdaten |
| 5 Euro-Wirkung | AP: Doppel-/Überzahlungen, Skontoverlust, Zahlung kurz nach Bankdatenänderung, Zahlung an gesperrte Kreditoren. AR: Unapplied Cash, Umbuchungen, ungerechtfertigtes Skonto, gesplittetes Kreditlimit. Netting gegen Gutschriften/Stornos | Prozess-Checks |
| 6 Ergebnis | Score je BP/Kategorie/gesamt (€-gewichtet), Findings-Explorer, Executive Summary, Excel je Kategorie, Massenänderungslisten (XD99/XK99-Format), Delta zwischen Läufen | Benchmarks |
| 7 Workflow-light | Zuweisen, Status, Kommentar, Auto-Close im nächsten Lauf | Write-back |
| 8 Anreicherung | VIES, IBAN→BIC, EU-Sanktionsliste offline | Register, Adressvalidierung |
| 9 Admin | Mandanten, BUKRS, Rollen, Audit-Log | SSO |

Nicht-Ziele V1: ERP-Write-back, allgemeines MDM, Materialstammdaten, Konzernhierarchie.

## 4. Stufenmodell – Balance zwischen Abdeckung und Richtigkeit

| Stufe | Bedingung | Ziel-Präzision | Darstellung |
|---|---|---|---|
| A „Soll" | deterministisch (VIES, Prüfziffer, T052) **oder** zwei unabhängige Quellen ohne Widerspruch | ≥ 99 % | Massenänderungsliste |
| B „Vorschlag" | eine starke Quelle oder Modell-Score über Schwelle | ≥ 90 % | Review-Queue |
| C „Hinweis" | eine schwache Quelle / Graubereich | keine Zusage | nur „prüfen" |
| decision | keine Datenlage ersetzt die Entscheidung | – | Optionen aufbereitet |

**Zwei-Quellen-Regel:** Ein Soll braucht eine autoritative Quelle (VIES, Register, GLEIF)
oder zwei unabhängige beobachtete (Kontoauszug + Zahllauf, Rechnung + Dublette).
Quellenhierarchie: extern autoritativ > beobachtetes Verhalten > interne Dublette >
Statistik > Modell.

**Konfidenz wird als Quellenlage gezeigt** („bestätigt durch VIES und Rechnung 4711"),
nicht als Prozentzahl. Bei Widerspruch zwischen Quellen: kein Soll, Stufe C.

## 5. Schadensklassen – die Schwelle hängt am Schaden, nicht am Feld

| Klasse | Felder | Regel |
|---|---|---|
| 1 | IBAN/Bankdaten | **nie Stufe A, nie Massenänderung.** Immer Review mit Vier-Augen. AP: Hinweis „Rückruf beim Lieferanten über bekannte Nummer" |
| 2 | USt-ID, Steuernummer, Zahlungsbedingung, Kreditlimit, Dubletten-Merge | Stufe A nur mit autoritativer Bestätigung (VIES). Merge nur bei gleicher USt-ID/Register-ID |
| 3 | Adresse, Name, Kontakt, Sperren, Löschvormerkung | Stufe A mit Korroboration; reversibel |

**Verdiente Automatisierung:** Lauf 1 beim Kunden = alles maximal Stufe B. Jede Review-
Entscheidung wird je Regel gezählt. ≥ 99 % Bestätigung über ≥ 50 Fälle → Regel wird für
diesen Kunden A. Fällt sie unter Ziel → automatisch zurück. Sichtbar im UI.

## 6. Ausgabe nach Aktionstyp

1. `mass_change` – fertige Liste (Schlüssel, BUKRS, Feld, alt, neu, Quelle, Stufe)
2. `review` – Vorschlag mit Evidenz, übernehmen/ablehnen (Grund Pflicht → Whitelist)
3. `decision` – Optionen mit Daten, Kunde entscheidet (ggf. per Policy automatisierbar)
4. `process` – Empfehlung an Prozessverantwortliche (Skonto, Vier-Augen bei Bankdaten)

Tempo ohne Kontrollverlust: **Stichproben-Freigabe** – 10 zufällige Findings einer
Stufe-A-Regel bestätigen → alle freigeben, Stichprobe bleibt im Audit-Trail.

## 7. Hebel für mehr Abdeckung (Reihenfolge nach Wirkung/Aufwand)

1. Interne Quellen: FEBEP/FEBKO, REGUH/REGUP, SEPA-Mandate, CDHDR/CDPOS, VBRK, EKKO, SGTXT
2. Policies statt Entscheidungen (Kunde definiert einmal, Tool wendet an)
3. Rechnungsdaten aus OCR (Stamm vs. Beleg)
4. Lernen: Review-Feedback → Schwellen, Whitelist-Muster; LLM als Tie-Breaker mit Begründung
5. Externe Anreicherung: GLEIF, Register/North Data, Creditreform/D&B, Adressvalidierung

Realistische Grenze: 85–90 % der Findings mit Vorschlag; 5–10 % bleiben bewusst Entscheidung.

## 8. Datenquellen SAP ECC

**Minimal-Set V1 (5–6 Exports je Seite):**
AR: KNA1, KNB1, KNBK + TIBAN, KNVP, Posten (BSID/BSAD oder FBL5N), T052
AP: LFA1, LFB1, LFBK + TIBAN, Posten (BSIK/BSAK oder FBL1N), T052

**Erweiterung:** KNVV, KNB5, ADRC/ADR6, KNKK, KNVI/KNAS, CDHDR/CDPOS (DEBI/KRED),
FEBEP/FEBKO, REGUH/REGUP. Details: `docs/extraction/SAP-ECC-EXTRACTION.md`,
Feldmapping: `logic/mappings/sap_ecc.yaml`.

Sonderfälle: CpD-Konten (XCPDK) aus Dubletten ausschließen; T077D/T077K nutzen, um
„Pflichtfeld laut Kontengruppe leer" von „leer, aber optional" zu trennen; Posten auf
12–24 Monate begrenzen; MANDT/BUKRS-Scoping; ALPHA-Konvertierung überall.

S/4: KNA1/KNB1/KNVV bleiben (CVI), BSID/BSAD sind Views auf ACDOCA, dazu BUT000/BUT0ID/
BUT0BK. ~90 % Wiederverwendung. Verkaufsargument: BP-Konvertierung scheitert an Dubletten.

## 9. UI-Leitlinien (Prototyp)

Review-Karte als Kern: Kopf (BP, Typ, Stufe, Schadensklasse, €, Aktionstyp) → Ist | Soll
nebeneinander mit Tabelle.Feld und Rohwert → Evidenz-Panel (jede Quelle eine Karte,
Übereinstimmung grün / Widerspruch rot, Zeitstrahl bei Änderungen) → Rechnung offen
(„32.000 € × 2 % = 640 €") → Warum / Wenn falsch → Wie beheben → Aktionen mit
Tastatur (J/K, A/R). Dubletten als Feld-für-Feld-Vergleich mit Match-Gründen.
Doppelzahlungen als Belegpaar mit Fuzzy-Grund und Netting-Nachweis.
Look: ruhig, dicht, neutral, Monospace für IDs/Beträge, Drawer statt Seitenwechsel.
Überall Datenstand-Banner.

## 10. Pipeline und Qualitätsprinzipien

`raw → staged → canonical → findings`, jede Stufe materialisiert, Raw unveränderlich,
Rejects sichtbar, Kontrollsummen gegen Kunden-Saldenliste, alles versioniert
(Engine, Regelpaket, Wörterbuch), deterministisch, DECIMAL für Geld, Encoding erkannt
statt angenommen, Golden Dataset (Demo-Mandant + erwartete Findings) als Regression.
