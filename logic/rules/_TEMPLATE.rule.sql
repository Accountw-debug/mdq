/* ---
id: XX-XXX-000
version: "1.0"
title: "Kurzüberschrift"
side: AR
category: validity
severity: medium
damage_class: 3
default_tier: B
default_action_type: review
requires_tables: [business_partner]
plain_logic: >
  In einem Satz: Welche Bedingung führt zu einem Finding, welche Ausschlüsse gelten.
why: >
  Warum ist das ein Problem und was passiert, wenn es nicht behoben wird.
if_wrong: >
  Was passiert, wenn der Vorschlag falsch übernommen wird.
remediation:
  sap_transaction: XD02
  path: null
  field: null
  mass_change_eligible: false
tests:
  hits: []
  no_hits: []
  edge: []
--- */
SELECT
    bp.bp_key,
    bp.role,
    NULL            AS company_code,
    'KNA1'          AS source_table,
    'FELD'          AS source_field,
    NULL            AS current_value,
    NULL            AS current_display,
    NULL            AS proposed_value,
    NULL            AS proposed_display,
    NULL            AS source_summary
FROM business_partner bp
WHERE FALSE
ORDER BY bp.bp_key;
