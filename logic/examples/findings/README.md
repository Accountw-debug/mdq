# Beispiel-Findings – die fachliche Spec

Ziel: 30 Findings über alle Typen, geschrieben so, wie ein Buchhalter sie lesen soll.
Jede Datei ist ein vollständiges Finding im Schema `logic/finding.schema.json` und wird
im Test validiert. Diese Beispiele sind Vorlage für UI (Review-Karte) und Engine (Ausgabe).

Sechs Muster liegen vor. Fehlende Typen (Victor ergänzt):
- AR: USt-ID fehlt (completeness), IBAN fehlt bei Lastschrift, Zahlungsbedingung leer,
  PLZ passt nicht zum Land, Adresse "Test"/"unbekannt", Debitor ohne Umsatz seit 24 Monaten,
  gleiche IBAN bei zwei Debitoren (Regulierer vs. Dublette), Unapplied Cash / Akontozahlung,
  Umbuchung zwischen Debitoren, gesplittetes Kreditlimit, ungerechtfertigt gewährtes Skonto
- AP: Kreditoren-Dublette, IBAN-Land ≠ Sitzland, Bankdatenänderung kurz vor Zahlung,
  Zahlung an gesperrten Kreditor, REPRF nicht gesetzt, Skontoverlust (process),
  Überzahlung, fehlende USt-ID bei EU-Lieferant
- CROSS: Kunde = Lieferant (gleiche USt-ID), Aufrechnungspotenzial

Namenskonvention: `F-<laufende Nr>-<rule_id>.yaml`. Beträge immer als String mit zwei
Dezimalen. Keine echten Firmen oder Personen – nur erfundene.

Der `relevance`-Block trägt `open_items`, `volume_12m`, `currency` (Hauswährung, Pflicht)
und `last_activity_on`. Beträge werden nicht umgerechnet – die Währung steht daneben (D-030).

Seit Schema 1.1 (D-069) gibt es vier weitere optionale Felder: `evidence[].reference_kind`
(was die Referenz ist), Belegdaten in `entity.documents[]` (`reference`, `document_date`,
`cleared_on`, `amount`, `currency`), `entity.records[]` (je Konto die Vergleichsfelder) und
`proposed.golden_record` (je Feld der beste Wert mit Herkunft). Gefüllt wird nur, was in der
Datei belegt ist – ein Feld, dessen Wert nirgends steht, bleibt weg. IBANs nur maskiert.
