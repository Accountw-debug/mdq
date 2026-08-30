/* ---
id: AR-VAL-001
version: "1.0"
title: "USt-ID-Präfix passt nicht zum Sitzland ({country})"
side: AR
category: validity
severity: high
damage_class: 2
default_tier: B
default_action_type: review
requires_tables: [business_partner, bp_tax_id]
plain_logic: >
  Finding, wenn ein Debitor (kein CpD) eine USt-ID (STCEG) hat, deren erste zwei Zeichen
  ein Buchstabenpräfix bilden, das nicht dem erwarteten Präfix seines Sitzlandes (LAND1)
  entspricht. Griechenland erwartet "EL", Nordirland "XI"; alle anderen EU-Länder ihren
  ISO-2-Code. Länder ohne EU-USt-ID (z. B. CH, US) werden nicht geprüft. Werte ohne
  Buchstabenpräfix (etwa eine Steuernummer im Feld STCEG) behaupten kein Land und sind
  deshalb kein Präfix-, sondern ein Formatfehler – sie gehören zu AR-VAL-002. Vorschlag:
  Präfix durch das erwartete ersetzen – Stufe B, weil ohne VIES-Bestätigung; mit
  VIES-Bestätigung würde die Engine auf A heben.
why: >
  Eine USt-ID mit falschem Länderpräfix scheitert bei der qualifizierten Bestätigung und
  gefährdet die steuerfreie innergemeinschaftliche Lieferung bzw. Reverse Charge. Auf
  Rechnungen ist sie Pflichtangabe nach § 14 UStG.
if_wrong: >
  Wird ein falsches Präfix übernommen, bleibt die ID ungültig – kein Geldschaden, aber die
  Korrektur muss wiederholt werden. Deshalb vor Übernahme VIES-Prüfung.
remediation:
  sap_transaction: XD02
  path: "Steuerung → USt-IdNr."
  field: STCEG
  mass_change_eligible: false
tests:
  hits: []
  no_hits: []
  edge: []
--- */
WITH expected AS (
    SELECT
        bp.bp_key,
        bp.role,
        bp.country,
        t.value                                   AS vat_value,
        t.value_norm                              AS vat_norm,
        CASE bp.country
            WHEN 'GR' THEN 'EL'
            ELSE bp.country
        END                                       AS expected_prefix
    FROM business_partner bp
    JOIN bp_tax_id t
      ON t.bp_key = bp.bp_key AND t.tax_id_type = 'VAT'
    WHERE bp.role = 'CUSTOMER'
      AND bp.is_one_time = FALSE
      AND bp.country IN ('AT','BE','BG','HR','CY','CZ','DK','EE','FI','FR','DE','GR','HU','IE','IT',
                         'LV','LT','LU','MT','NL','PL','PT','RO','SK','SI','ES','SE')
      AND length(t.value_norm) >= 4
      -- Ohne Buchstabenpraefix behauptet der Wert kein Land: das ist ein Formatfehler
      -- (AR-VAL-002), kein Praefixfehler (D-058)
      AND regexp_matches(substr(t.value_norm, 1, 2), '^[A-Z]{2}$')
)
SELECT
    e.bp_key,
    e.role,
    NULL                                          AS company_code,
    'KNA1'                                        AS source_table,
    'STCEG'                                       AS source_field,
    e.vat_value                                   AS current_value,
    NULL                                          AS current_display,
    e.expected_prefix || substr(e.vat_norm, 3)    AS proposed_value,
    NULL                                          AS proposed_display,
    'Sitzland ' || e.country || ' erwartet Präfix ' || e.expected_prefix
        || ' – ohne VIES-Bestätigung'             AS source_summary,
    to_json([{
        'source_type': 'deterministic',
        'reference':   'KNA1.LAND1',
        'value':       e.country,
        'observed_at': NULL,
        'agrees':      TRUE,
        'note':        'Präfix aus Sitzland abgeleitet'
    }])                                           AS evidence,
    to_json({'country': e.country, 'expected_prefix': e.expected_prefix})  AS params
FROM expected e
WHERE substr(e.vat_norm, 1, 2) <> e.expected_prefix
ORDER BY e.bp_key;
