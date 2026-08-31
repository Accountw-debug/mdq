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
| **Nachweisart (reference_kind)** | Was die Referenz einer Evidenz ist: `document` (FI-Beleg `BUKRS/GJAHR/BELNR`), `master_field` (Stammfeld wie `KNA1.LAND1`), `cluster` (Dubletten-Cluster), `external_query` (externe Abfrage, z. B. VIES), `statement` (Postenübersicht über ein Konto und einen Zeitraum), `netting` (Suche nach Gutschrift/Storno), `payment_run` (Zahllauf), `policy`. Die `source_type` sagt das nicht: Beleg, Stammfeld und Cluster stehen alle unter `deterministic` bzw. `model`. Optional – ohne Angabe zeigt die UI die Referenz wörtlich |
| **Quellenlage** | Menschenlesbare Zusammenfassung der Evidenzen („bestätigt durch VIES und Rechnung 4711") |
| **Herkunft (source)** | Woher ein normalisierter Wert im Staging stammt: `dictionary`, `regex` oder `model`. Steht zusammen mit einer Konfidenz an jedem normalisierten Feld; ein Finding auf einem `model`-Feld kommt ohne zweite Quelle nicht über Stufe B (D-067) |
| **Hauswährung (company_code.currency)** | Währung, in der ein Buchungskreis seine Beträge führt (`T001.WAERS`, in SAP das Feld hinter `DMBTR`). Nicht die Belegwährung `WAERS` eines Postens: eine Fremdwährungsrechnung steht in USD, ihr `DMBTR` trotzdem in der Hauswährung. V1 rechnet nicht um – kommen im Scope eines Laufs mehrere Hauswährungen vor, bricht der Lauf ab (D-030, D-083) |
| **Euro-Wirkung (impact_eur)** | Betrag mit offengelegter Rechnung |
| **Offene Posten (open_items)** | Summe der am Datenstand nicht ausgeglichenen Posten des BP in Hauswährung |
| **Volumen 12 Monate (volume_12m)** | Summe der Rechnungsbeträge (brutto, Belegarten Rechnung) mit Buchungsdatum in den 12 Monaten vor dem Datenstand, abzüglich Gutschriften im selben Fenster – **unabhängig davon, ob die Rechnung ausgeglichen ist**. Zusammen mit den offenen Posten das Relevanzgewicht eines BP |
| **Relevanzfenster** | Die zwölf Monate vor dem Datenstand, **links offen und rechts geschlossen**: `posting_date > data_as_of − 12 Monate` und `<= data_as_of`. Dasselbe Fenster gilt für `volume_12m` und für den Aktivitätsstatus – ein Aktualitätsbegriff, nicht zwei (D-086, D-087) |
| **Letzte Aktivität (last_activity_on)** | Spätestes Datum aus Buchungs- und Ausgleichsdatum aller Posten des BP. Ein Konto ohne Posten hat keine letzte Aktivität (`null`) |
| **Aktivitätsstatus (activity_status)** | `active` – letzte Aktivität im Relevanzfenster; `dormant` – keine Aktivität im Fenster, einschließlich der Konten ganz ohne Posten, die vor Fensterbeginn angelegt wurden; `never_posted` – kein Posten und Anlage im Fenster, das Konto konnte sich noch nicht bewegen (D-086) |
| **Golden Record** | Vorschlag für das führende Konto (`proposed.value`) und je Feld den besten Wert mit seiner Herkunft (`proposed.golden_record`: je Feld `value`, `source_bp_key`, `source_type`) |
| **Kontosatz (entity.records)** | Je beteiligtem Konto die Vergleichsfelder in Feldform statt als Fließtext: Name, Straße, PLZ, Ort, Land, USt-ID, maskierte IBAN, Zahlungsbedingung, offene Posten, Währung, letzte Aktivität. Grundlage des Feld-für-Feld-Vergleichs bei Dubletten. Beträge als String mit zwei Dezimalen, IBAN nur maskiert (höchstens die ersten vier und die letzten vier Zeichen, Regel 8) |
| **Survivorship** | Regeln, welcher Wert je Feld gewinnt (VIES-geprüft > zuletzt geändert > vollständigster) |
| **Entscheidungsgedächtnis (decision_memory)** | Gepflegte Datei mit getroffenen Entscheidungen (`--decisions`, ersatzweise `<input>/decisions.yaml`), je Eintrag `finding_id`, `rule_id`, `bp_key`, `decided_by`, `decided_at`, `reason_code`, `reason`. Das Finding entsteht weiterhin und trägt den gespeicherten Status statt `open` – nichts verschwindet stumm. Kein Laufprodukt: es wird nicht aus dem `findings.json` eines Vorlaufs gelesen (D-088) |
| **Whitelist** | Vom Kunden abgelehnte Vorschläge/„bewusst getrennt"-Paare, bleiben über Läufe |
| **Policy** | Kundenregel, die einen `decision`-Fall deterministisch macht |
| **Lauf (run)** | Unveränderlicher Snapshot: Input-Hashes, Versionen, Datenstand, Findings |
| **Lauf-Kennung (run_id)** | `<data_as_of>-<kurzhash>`: der Kurzhash steht für die Input-Hashes, den Scope, den Datenstand und die Entscheidungsdatei – nicht für Engine- oder Paketversion. Derselbe Datenstand mit derselben Frage ist derselbe Lauf (D-093) |
| **Regelpaket (pack_version)** | Version der fachlichen Logik in `logic/` (Schema, Regeln, Mappings), gepflegt in `logic/pack.yaml`; `dict_version` versioniert die Wörterbücher. Ob das Paket unverändert war, zeigt `versions.pack_hash` – ein sha256 über alle Dateien unter `logic/` (D-096) |
| **Hinweis vs. Auffälligkeit** | Hinweis: etwas, das der Lauf sagt, ohne dass es ihn beeinträchtigt (leere `name_norm`, Belegart ohne Klasse, verwaiste Entscheidung) – steht in `run.json` unter `hints`. Auffälligkeit: Rejects, übersprungene oder fehlgeschlagene Regeln – `has_problems` wird wahr und der Lauf endet mit Exit 1 (D-097) |
| **Datenstand (data_as_of)** | Datum des Exports beim Kunden |
| **Demo-Mandant** | Synthetischer SAP-Datensatz mit eingebauten Fehlern (`testdata/demo_mandant`) |
| **Regression** | Lauf auf dem Demo-Mandanten muss exakt `testdata/expected/` liefern |
| **Reject** | Zeile, die nicht verarbeitet werden konnte, mit Grund – nie stumm verworfen |
| **CpD** | Conto pro Diverse, Einmalkunde/-lieferant (`XCPDK`), aus Dubletten ausgeschlossen |
| **Regulierer** | Partnerrolle RG (KNVP) bzw. abweichender Zahler (KNRZA/KNRZB) |
| **Kanonisches Schema** | ERP-unabhängiges Zielmodell, `logic/schema/canonical.sql` |
| **KI-Schicht** | Modellgestützte Zerlegung unsauberer Texte im Staging, **vor** dem kanonischen Modell: Wörterbuch → Regex → Modell. Extraktion, nicht Entscheidung – Regeln bleiben SQL, Euro-Beträge kommen nie aus einem Modell (D-067, Sprint 4b) |
