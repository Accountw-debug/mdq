/* ---
id: AP-VAL-003
version: "1.0"
title: "IBAN mit ungültiger Prüfziffer ({iban_masked})"
side: AP
category: validity
severity: critical
damage_class: 1
default_tier: C
default_action_type: review
requires_tables: [business_partner, bp_bank_account]
plain_logic: >
  Finding, wenn eine Bankverbindung eines Kreditors (kein CpD) eine IBAN trägt, deren
  Prüfziffer nach ISO 13616 (Mod-97) falsch ist. Bankverbindungen ohne IBAN werden nicht
  geprüft – dort gibt es nichts zu rechnen, und ein Finding wäre eine Behauptung ohne
  Grundlage. Kein Soll: aus einer falschen IBAN folgt keine richtige, deshalb Stufe C und
  ein Vorgehen statt eines Wertes. Schadensklasse 1 – nie Stufe A, nie Massenänderung,
  auch nicht per Policy. Im Finding steht die IBAN ausschließlich maskiert (Regel 8);
  auffindbar bleibt die Bankverbindung über Bankschlüssel (BANKL) und Bankdetail-ID
  (BVTYP), die beide keine Kontonummer nennen (D-105).
why: >
  Eine IBAN mit falscher Prüfziffer wird von der Bank abgewiesen – die Zahlung bleibt
  liegen und die Verbindlichkeit wird überfällig – oder sie trifft, wenn die verdrehte
  Stelle zufällig ein gültiges Konto ergibt, einen fremden Empfänger. Beim Kreditor geht
  das Geld aus dem Haus: falsche Bankdaten im Lieferantenstamm sind der häufigste
  Betrugsvektor (gefälschte Kontoänderung per Brief oder Mail).
if_wrong: >
  Eine falsch korrigierte IBAN ist eine Fehlüberweisung an einen Dritten und praktisch
  nicht rückholbar. Deshalb nie automatisch übernehmen, sondern über einen bekannten
  Kanal beim Lieferanten bestätigen lassen – nicht über eine Nummer aus dem Schreiben,
  das die Änderung ankündigt. Die richtige IBAN steht in keinem anderen Feld des
  Mandanten; deshalb nennt das Finding kein Soll, sondern ein Vorgehen.
remediation:
  sap_transaction: XK02
  path: "Zahlungsverkehr → Bankverbindungen"
  field: IBAN
  mass_change_eligible: false
  steps:
    - "Lieferant über eine bekannte Telefonnummer kontaktieren, nicht über den Kontaktweg aus der Änderungsmitteilung"
    - "IBAN gegen ein zweites Dokument abgleichen (Vertrag, Rechnungsbild, Kontoauszug)"
    - "Änderung mit Vier-Augen-Freigabe in XK02"
tests:
  # Nur Konten, die `testdata/demo_mandant/defects.yaml` namentlich nennt (D-066).
  hits:
    - "V:0000201330"   # DEF-0006, Anker F-006: Pruefziffer verdreht
    - "V:0000200072"   # DEF-0046
    - "V:0000200077"   # DEF-0046
  no_hits:
    - "V:0000200845"   # DEF-0004, Anker F-004: gueltige IBAN
    - "V:0000200117"   # DEF-0005, Anker F-005: gueltige IBAN
  edge:
    # Dieselbe Datenlage auf der AR-Seite: diese Regel darf sie nicht liefern, das ist
    # AR-VAL-003. Ein fehlender Rollenfilter faellt hier auf.
    - "C:0000100147"   # DEF-0045
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
    to_json({
        'iban_masked':        substr(b.iban_norm, 1, 4) || ' … ' || substr(b.iban_norm, -4),
        'bank_key':           b.bank_key,
        'partner_bank_type':  b.partner_bank_type
    })                                            AS params
FROM bp_bank_account b
JOIN business_partner bp
  ON bp.bp_key = b.bp_key
WHERE bp.role = 'VENDOR'
  AND bp.is_one_time = FALSE
  -- NULL heisst "keine IBAN hinterlegt": nicht geprueft, kein Finding
  AND b.iban_valid = FALSE
ORDER BY bp.bp_key, b.iban_norm;
