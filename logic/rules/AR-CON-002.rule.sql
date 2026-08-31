/* ---
id: AR-CON-002
version: "1.0"
title: "Löschvormerkung/Buchungssperre bei Debitor mit offenen Posten ({open_items})"
side: AR
category: consistency
severity: high
damage_class: 3
default_tier: decision
default_action_type: decision
requires_tables: [business_partner, bp_company_code, fi_item]
plain_logic: >
  Finding je Buchungskreis, wenn ein Debitor zentral oder im Buchungskreis zur Löschung
  vorgemerkt oder für Buchungen gesperrt ist und gleichzeitig offene Posten in diesem
  Buchungskreis hat. CpD-Konten ausgeschlossen. Keine automatische Empfehlung, weil beides
  legitim sein kann (Sperre wegen Insolvenz vs. vergessene Löschvormerkung).
why: >
  Ein gesperrtes oder zur Löschung vorgemerktes Konto mit offenen Posten wird im Mahnlauf
  und in der Zahlungszuordnung inkonsistent behandelt; bei der S/4-Konvertierung blockiert
  die Löschvormerkung die Übernahme offener Posten.
if_wrong: >
  Wird die Sperre fälschlich entfernt, können Buchungen auf ein Konto laufen, das bewusst
  gesperrt war (z. B. Insolvenz). Deshalb Entscheidung durch den Kunden.
remediation:
  sap_transaction: XD05 / XD06
  path: "XD05 Sperre setzen/aufheben, XD06 Löschvormerkung"
  field: SPERR / LOEVM
  mass_change_eligible: false
  steps:
    - "Grund der Sperre/Löschvormerkung klären (Änderungsbeleg, Sachbearbeiter)"
    - "Option A: Sperre/Löschvormerkung aufheben, Posten normal weiterverfolgen"
    - "Option B: Posten ausgleichen oder umbuchen, Löschvormerkung beibehalten"
tests:
  # Nur Konten, die `testdata/demo_mandant/defects.yaml` namentlich nennt (D-066).
  hits:
    - "C:0000101502"   # DEF-0003, Anker F-004: Loeschvormerkung zentral, 3 offene Posten
    - "C:0000100000"   # DEF-0008: Loeschvormerkung zentral bei offenen Posten
    - "C:0000100002"   # DEF-0009: Buchungssperre im Buchungskreis bei offenen Posten
  no_hits:
    - "C:0000100001"   # DEF-0012: Loeschvormerkung ohne offene Posten - stillgelegt, kein Fehler
    - "C:0000100134"   # DEF-0013: Loeschvormerkung ohne offene Posten
  edge:
    # Offene Posten in beiden Buchungskreisen: die Regel liefert zwei Findings, je eines
    # mit gesetztem entity.company_code (D-055).
    - "C:0000100028"   # DEF-0007
--- */
WITH open_sum AS (
    SELECT bp_key, company_code, currency,
           SUM(amount_signed_local) AS open_local
    FROM fi_item
    WHERE is_open = TRUE
    GROUP BY bp_key, company_code, currency
)
SELECT
    bp.bp_key,
    bp.role,
    cc.company_code,
    CASE WHEN bp.deletion_flag OR bp.central_block THEN 'KNA1' ELSE 'KNB1' END  AS source_table,
    CASE
        WHEN bp.deletion_flag THEN 'LOEVM'
        WHEN bp.central_block THEN 'SPERR'
        WHEN cc.deletion_flag THEN 'LOEVM'
        ELSE 'SPERR'
    END                                                                         AS source_field,
    'X'                                                                         AS current_value,
    CASE
        WHEN bp.deletion_flag OR cc.deletion_flag THEN 'Löschvormerkung gesetzt'
        ELSE 'Buchungssperre gesetzt'
    END                                                                         AS current_display,
    NULL                                                                        AS proposed_value,
    NULL                                                                        AS proposed_display,
    'Offene Posten ' || mdq_money(o.open_local, o.currency)
        || ' bei gesetzter Sperre/Löschvormerkung'                              AS source_summary,
    to_json([
        {'label': 'Sperre/Löschvormerkung aufheben',
         'consequence': 'Konto wird wieder normal gemahnt und bebucht'},
        {'label': 'Posten ausgleichen/umbuchen, Kennzeichen beibehalten',
         'consequence': 'Konto bleibt gesperrt, offene Posten müssen manuell bereinigt werden'}
    ])                                                                          AS options,
    to_json([{
        'source_type': 'deterministic',
        'reference':   'BSID ' || cc.company_code,
        -- Freitext, kein Datenfeld: der Betrag steht deutsch mit Waehrung (D-187).
        'value':       mdq_money(o.open_local, o.currency),
        'observed_at': NULL,
        'agrees':      TRUE,
        'note':        'Summe offene Posten im Buchungskreis'
    }])                                                                         AS evidence,
    o.open_local                                                                AS impact_amount,
    o.currency                                                                  AS impact_currency,
    'Summe offener Posten im Buchungskreis ' || cc.company_code                 AS impact_formula,
    to_json({'open_items': mdq_money(o.open_local, o.currency), 'currency': o.currency})  AS params
FROM business_partner bp
JOIN bp_company_code cc ON cc.bp_key = bp.bp_key
JOIN open_sum o         ON o.bp_key = bp.bp_key AND o.company_code = cc.company_code
WHERE bp.role = 'CUSTOMER'
  AND bp.is_one_time = FALSE
  AND (bp.deletion_flag OR bp.central_block OR cc.deletion_flag OR cc.posting_block)
  AND o.open_local <> 0
ORDER BY bp.bp_key, cc.company_code;
