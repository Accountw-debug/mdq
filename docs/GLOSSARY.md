# Glossar – diese Begriffe gelten in Code, UI und Doku

| Begriff | Bedeutung |
|---|---|
| **BP / Geschäftspartner** | Debitor oder Kreditor im kanonischen Modell. Schlüssel `bp_key` = `C:<KUNNR>` bzw. `V:<LIFNR>` |
| **Seite (side)** | `AR` (Debitoren), `AP` (Kreditoren), `CROSS` (beide) |
| **Finding** | Eine Feststellung einer Regel zu einem BP oder Beleg(paar). Zentrales Objekt, Schema `logic/finding.schema.json` |
| **Regel (rule)** | Eine SQL-Query auf dem kanonischen Schema mit YAML-Kopf. ID-Format `<SEITE>-<KAT>-<NNN>`, z. B. `AR-VAL-001` |
| **Kategorie (category)** | `completeness`, `validity`, `consistency`, `hygiene`, `risk`, `duplicate`, `leakage` |
| **Geldabfluss (leakage)** | Kategorie für Findings mit echtem Geldabfluss: Doppel- und Überzahlungen, Skontoverlust, Unapplied Cash. Abgrenzung: Stammdatenfehler ohne Zahlungswirkung sind `validity` oder `consistency` |
| **Schwere (severity)** | `low`, `medium`, `high`, `critical` – Dringlichkeit für den Kunden |
| **Schadensklasse (damage_class)** | 1 = Geldwirkung bei Fehlkorrektur (Bankdaten), 2 = steuerlich/vertraglich, 3 = reversibel |
| **Stufe (tier)** | `A` Soll (≥ 99 %), `B` Vorschlag (≥ 90 %), `C` Hinweis, `decision` Entscheidung |
| **Aktionstyp (action_type)** | `mass_change`, `review`, `decision`, `process` |
| **Ist (current)** | Wert wie im SAP, mit Tabelle und Feld |
| **Soll (proposed)** | Vorgeschlagener Wert mit Quellenlage |
| **Evidenz (evidence)** | Einzelne Quelle mit Wert, Referenz, Datum, Übereinstimmung |
| **Quellenlage** | Menschenlesbare Zusammenfassung der Evidenzen („bestätigt durch VIES und Rechnung 4711") |
| **Herkunft (source)** | Woher ein normalisierter Wert im Staging stammt: `dictionary`, `regex` oder `model`. Steht zusammen mit einer Konfidenz an jedem normalisierten Feld; ein Finding auf einem `model`-Feld kommt ohne zweite Quelle nicht über Stufe B (D-067) |
| **Euro-Wirkung (impact_eur)** | Betrag mit offengelegter Rechnung |
| **Offene Posten (open_items)** | Summe der am Datenstand nicht ausgeglichenen Posten des BP in Hauswährung |
| **Volumen 12 Monate (volume_12m)** | Summe der Rechnungsbeträge (brutto, Belegarten Rechnung) mit Buchungsdatum in den 12 Monaten vor dem Datenstand, abzüglich Gutschriften im selben Fenster – **unabhängig davon, ob die Rechnung ausgeglichen ist**. Zusammen mit den offenen Posten das Relevanzgewicht eines BP |
| **Letzte Aktivität (last_activity_on)** | Spätestes Datum aus Buchungs- und Ausgleichsdatum aller Posten des BP. Ein Konto ohne Posten hat keine letzte Aktivität (`null`) |
| **Golden Record** | Vorschlag für das führende Konto und je Feld den besten Wert bei Dubletten |
| **Survivorship** | Regeln, welcher Wert je Feld gewinnt (VIES-geprüft > zuletzt geändert > vollständigster) |
| **Whitelist** | Vom Kunden abgelehnte Vorschläge/„bewusst getrennt"-Paare, bleiben über Läufe |
| **Policy** | Kundenregel, die einen `decision`-Fall deterministisch macht |
| **Lauf (run)** | Unveränderlicher Snapshot: Input-Hashes, Versionen, Datenstand, Findings |
| **Datenstand (data_as_of)** | Datum des Exports beim Kunden |
| **Demo-Mandant** | Synthetischer SAP-Datensatz mit eingebauten Fehlern (`testdata/demo_mandant`) |
| **Regression** | Lauf auf dem Demo-Mandanten muss exakt `testdata/expected/` liefern |
| **Reject** | Zeile, die nicht verarbeitet werden konnte, mit Grund – nie stumm verworfen |
| **CpD** | Conto pro Diverse, Einmalkunde/-lieferant (`XCPDK`), aus Dubletten ausgeschlossen |
| **Regulierer** | Partnerrolle RG (KNVP) bzw. abweichender Zahler (KNRZA/KNRZB) |
| **Kanonisches Schema** | ERP-unabhängiges Zielmodell, `logic/schema/canonical.sql` |
| **KI-Schicht** | Modellgestützte Zerlegung unsauberer Texte im Staging, **vor** dem kanonischen Modell: Wörterbuch → Regex → Modell. Extraktion, nicht Entscheidung – Regeln bleiben SQL, Euro-Beträge kommen nie aus einem Modell (D-067, Sprint 4b) |
