/* ---
id: AR-VAL-003
version: "1.2"
title: "IBAN mit ungültiger Prüfziffer ({iban_masked})"
side: AR
category: validity
severity: critical
damage_class: 1
default_tier: C
default_action_type: review
requires_tables: [business_partner, bp_bank_account, bp_relevance]
plain_logic: >
  Finding, wenn eine Bankverbindung eines Debitors (kein CpD) eine IBAN trägt, deren
  Prüfziffer nach ISO 13616 (Mod-97) falsch ist. Bankverbindungen ohne IBAN werden nicht
  geprüft – dort gibt es nichts zu rechnen, und ein Finding wäre eine Behauptung ohne
  Grundlage. Kein Soll: aus einer falschen IBAN folgt keine richtige, deshalb Stufe C und
  ein Vorgehen statt eines Wertes. Schadensklasse 1 – nie Stufe A, nie Massenänderung,
  auch nicht per Policy. Im Finding steht die IBAN ausschließlich maskiert (Regel 8);
  auffindbar bleibt die Bankverbindung über Bankschlüssel (BANKL) und Bankdetail-ID
  (BVTYP), die beide keine Kontonummer nennen (D-105).
  Euro-Wirkung: die offenen Posten des Debitors sind der Betrag, der über genau diese
  Bankverbindung per Lastschrift eingezogen würde. Er kommt aus
  `bp_relevance.open_items_local` und steht nur da, wo offene Posten existieren – ohne
  sie gibt es nichts zu beziffern, und eine 0,00 wäre eine Behauptung statt einer
  fehlenden Zahl (Regel 4).
why: >
  Eine IBAN mit falscher Prüfziffer wird von der Bank abgewiesen – die Zahlung bleibt
  liegen – oder sie trifft, wenn die verdrehte Stelle zufällig ein gültiges Konto ergibt,
  einen fremden Empfänger. Bei Debitoren betrifft das Lastschrifteinzug und Erstattungen.
if_wrong: >
  Eine falsch korrigierte IBAN ist eine Fehlüberweisung an einen Dritten und praktisch
  nicht rückholbar. Deshalb nie automatisch übernehmen, sondern über einen bekannten
  Kanal beim Kunden bestätigen lassen – nicht über eine Nummer aus dem Schreiben, das
  die Änderung ankündigt. Die richtige IBAN steht in keinem anderen Feld des Mandanten;
  deshalb nennt das Finding kein Soll, sondern ein Vorgehen.
remediation:
  sap_transaction: XD02
  path: "Zahlungsverkehr → Bankverbindungen"
  field: IBAN
  mass_change_eligible: false
  steps:
    - "Kunden über eine bekannte Telefonnummer kontaktieren, nicht über den Kontaktweg aus der Änderungsmitteilung"
    - "IBAN gegen ein zweites Dokument abgleichen (Vertrag, Kontoauszug, SEPA-Mandat)"
    - "Änderung mit Vier-Augen-Freigabe in XD02"
tests:
  # Nur Konten, die `testdata/demo_mandant/defects.yaml` namentlich nennt (D-066).
  hits:
    - "C:0000100147"   # DEF-0045: Pruefziffer verdreht
    - "C:0000100152"   # DEF-0045
    - "C:0000100157"   # DEF-0045
  no_hits:
    - "C:0000100234"   # DEF-0001, Anker F-001: gueltige IBAN
    - "C:0000100987"   # DEF-0002, Anker F-002: gueltige IBAN
  edge:
    # Dieselbe Datenlage auf der AP-Seite: diese Regel darf sie nicht liefern, das ist
    # AP-VAL-003 (Aufgabe 7). Ein fehlender Rollenfilter faellt hier auf.
    - "V:0000200072"   # DEF-0046
--- */
SELECT
    bp.bp_key,
    bp.role,
    NULL                                          AS company_code,
    'TIBAN'                                       AS source_table,
    'IBAN'                                        AS source_field,
    -- Schadensklasse 1: nur die ersten und letzten vier Stellen, nie die ganze IBAN
    -- (CLAUDE.md Regel 8, Maske nach logic/finding.schema.json $defs.iban_masked)
    substr(b.iban_norm, 1, 4) || ' … ' || substr(b.iban_norm, -4)  AS current_value,
    'Prüfziffer ungültig (Mod-97)'                AS current_display,
    -- Kein Soll und deshalb kein proposed (D-186): das Vorgehen steht unter remediation.
    NULL                                          AS proposed_value,
    NULL                                          AS proposed_display,
    NULL                                          AS source_summary,
    to_json([{
        'source_type': 'iban_checksum',
        -- Bankschluessel und Bankdetail-ID identifizieren die Bankverbindung im
        -- Stammsatz, ohne die Kontonummer zu nennen (D-105)
        'reference':   'TIBAN BANKL ' || coalesce(b.bank_key, '–')
                       || ' / BVTYP ' || coalesce(b.partner_bank_type, '–'),
        'value':       substr(b.iban_norm, 1, 4) || ' … ' || substr(b.iban_norm, -4),
        'observed_at': NULL,
        'agrees':      FALSE,
        'note':        'Mod-97-Prüfung fehlgeschlagen'
    }])                                           AS evidence,
    -- Euro-Wirkung: was ueber diese Bankverbindung per Lastschrift eingezogen wuerde.
    -- Ohne offene Posten traegt das Finding kein impact_eur - die Zahl fehlt dann, sie
    -- wird nicht als 0,00 behauptet (Regel 4).
    CASE WHEN r.open_items_local > 0 THEN r.open_items_local END    AS impact_amount,
    CASE WHEN r.open_items_local > 0 THEN r.currency END            AS impact_currency,
    CASE WHEN r.open_items_local > 0
         THEN 'Offene Posten ' || mdq_money(r.open_items_local, r.currency)
              || ', die über diese IBAN per Lastschrift eingezogen würden'
    END                                                             AS impact_formula,
    to_json({
        'iban_masked':        substr(b.iban_norm, 1, 4) || ' … ' || substr(b.iban_norm, -4),
        'bank_key':           b.bank_key,
        'partner_bank_type':  b.partner_bank_type
    })                                            AS params
FROM bp_bank_account b
JOIN business_partner bp
  ON bp.bp_key = b.bp_key
LEFT JOIN bp_relevance r
  ON r.bp_key = bp.bp_key
WHERE bp.role = 'CUSTOMER'
  AND bp.is_one_time = FALSE
  -- NULL heisst "keine IBAN hinterlegt": nicht geprueft, kein Finding
  AND b.iban_valid = FALSE
ORDER BY bp.bp_key, b.iban_norm;
