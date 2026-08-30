/* ---
id: AP-LEA-001
# Korrektur 2026-08-30 (D-082, Version bleibt 1.0 - der Klartext war immer richtig):
# Die netted-CTE erkannte ein Netting an `debit_credit = 'S'` allein. Beim Kreditor ist
# aber auch die Zahlung Soll, und jede bezahlte Rechnung hat eine Zahlung in gleicher
# Hoehe - die Regel nettete damit jedes Paar weg und fand nie etwas. Das SQL prueft
# zusaetzlich die Belegart und folgt damit dem Klartext (Regel 10).
#
# Belegarten stehen seit D-084 im Woerterbuch logic/dictionaries/document_types.yaml;
# die Engine setzt sie als ${doc_types.<Seite>.<Klasse>} ein, bevor sie das SQL ausfuehrt.
# Der Klartext nennt "Gutschrift/Storno"; die Klasse `reversal` ist heute leer, weil kein
# Export eine Stornobelegart geliefert hat (offener Punkt in D-082). Sobald eine vorliegt,
# wird sie dort eingetragen und hier zu ${doc_types.AP.credit_memo+reversal} erweitert -
# ohne Aenderung an dieser Datei waere es eine zweite Liste.
version: "1.0"
title: "Mögliche Doppelzahlung: {amount} {currency} an Kreditor, Referenz {ref_a} / {ref_b}"
side: AP
category: leakage
severity: critical
damage_class: 2
default_tier: B
default_action_type: review
requires_tables: [business_partner, fi_item]
plain_logic: >
  Zwei Kreditorenrechnungen (Belegart-Gruppe Rechnung, Soll/Haben = H) desselben
  Kreditors mit identischem Betrag in derselben Währung, Belegdatum maximal 60 Tage
  auseinander, deren normalisierte Referenzen (XBLNR ohne Sonderzeichen) gleich sind oder
  Levenshtein-Abstand ≤ 1 haben. Beide Posten müssen bezahlt (ausgeglichen) sein.
  Ausgeschlossen: Paare, für die eine Gutschrift/Storno in gleicher Höhe zum selben
  Kreditor innerhalb von 180 Tagen nach der zweiten Rechnung existiert (Netting).
  Kreditoren-Dubletten über Konten hinweg werden erst mit dem Dubletten-Cluster (AP-DUP)
  in Version 1.1 einbezogen.
why: >
  Doppelt erfasste und bezahlte Rechnungen sind abgeflossenes Geld. SAPs Doppelerfassungs-
  prüfung (REPRF) greift nur bei exakt gleicher Referenz, Datum und Betrag – abweichende
  Schreibweisen der Referenz umgehen sie.
if_wrong: >
  Wird ein Paar fälschlich als Doppelzahlung angemahnt, entsteht Aufwand beim Lieferanten
  und Reputationsschaden. Deshalb Review mit beiden Belegen nebeneinander, kein Automatismus.
remediation:
  sap_transaction: FBL1N
  path: "Belegpaar prüfen, dann Rückforderung/Verrechnung anstoßen"
  field: null
  mass_change_eligible: false
  steps:
    - "Beide Belege und Rechnungsbilder vergleichen"
    - "Rückforderung an Lieferant (Anschreiben-Vorlage) oder Verrechnung mit nächster Rechnung"
    - "Ursache prüfen: Kreditoren-Dublette, Referenz-Erfassung, REPRF-Kennzeichen (LFB1)"
tests:
  # Nur Konten, die `testdata/demo_mandant/defects.yaml` namentlich nennt (D-066).
  hits:
    - "V:0000200845"   # DEF-0004, Anker F-003: "RE-4711" / "RE4711", zweimal 32.000,00
    - "V:0000200151"   # DEF-0071: Referenzvariante am selben Konto
    - "V:0000200153"   # DEF-0073: Referenzvariante am selben Konto
  no_hits:
    - "V:0000200169"   # DEF-0078: durch Gutschrift innerhalb 180 Tagen genettet
    - "V:0000200170"   # DEF-0079: durch Gutschrift innerhalb 180 Tagen genettet
  edge:
    # Doppelzahlung ueber zwei Kreditorenkonten desselben Lieferanten: Version 1.0
    # vergleicht Belege eines Kontos und findet das Paar nicht - Pflicht ab 1.1 (D-054).
    - "V:0000200001"   # DEF-0081
--- */
WITH inv AS (
    SELECT i.*
    FROM fi_item i
    JOIN business_partner bp ON bp.bp_key = i.bp_key
    WHERE bp.role = 'VENDOR'
      AND i.debit_credit = 'H'                 -- Rechnung = Haben beim Kreditor
      AND i.doc_type IN (${doc_types.AP.invoice})   -- Woerterbuch, nicht Liste (D-084)
      AND i.is_open = FALSE
      AND i.reference_norm IS NOT NULL
),
pairs AS (
    SELECT
        a.bp_key,
        a.company_code,
        a.currency,
        a.amount_doc,
        a.item_key AS key_a, b.item_key AS key_b,
        a.fiscal_year AS year_a, b.fiscal_year AS year_b,
        a.document_no AS doc_a, b.document_no AS doc_b,
        a.reference AS ref_a, b.reference AS ref_b,
        a.document_date AS date_a, b.document_date AS date_b
    FROM inv a
    JOIN inv b
      ON a.bp_key = b.bp_key
     AND a.currency = b.currency
     AND a.amount_doc = b.amount_doc
     AND a.item_key < b.item_key
     AND abs(date_diff('day', a.document_date, b.document_date)) <= 60
     AND (a.reference_norm = b.reference_norm
          OR levenshtein(a.reference_norm, b.reference_norm) <= 1)
),
netted AS (
    SELECT p.key_a, p.key_b
    FROM pairs p
    JOIN fi_item g
      ON g.bp_key = p.bp_key
     AND g.debit_credit = 'S'                  -- Gutschrift/Storno = Soll beim Kreditor
     AND g.doc_type IN (${doc_types.AP.credit_memo})   -- die Zahlung ist auch Soll (D-082)
     AND g.currency = p.currency
     AND g.amount_doc = p.amount_doc
     AND g.document_date BETWEEN greatest(p.date_a, p.date_b)
                             AND greatest(p.date_a, p.date_b) + INTERVAL 180 DAY
)
SELECT
    p.bp_key,
    'VENDOR'                                            AS role,
    p.company_code,
    'BSAK'                                              AS source_table,
    'XBLNR'                                             AS source_field,
    p.ref_a || ' | ' || p.ref_b                         AS current_value,
    'Zwei bezahlte Rechnungen über ' || CAST(p.amount_doc AS VARCHAR) || ' ' || p.currency  AS current_display,
    NULL                                                AS proposed_value,
    'Rückforderung oder Verrechnung'                    AS proposed_display,
    'Belegpaar ' || p.doc_a || ' / ' || p.doc_b || ': gleicher Betrag, Referenz '
        || CASE WHEN p.ref_a = p.ref_b THEN 'identisch' ELSE 'nahezu identisch' END
        || ', ' || CAST(abs(date_diff('day', p.date_a, p.date_b)) AS VARCHAR)
        || ' Tage Abstand, keine Gutschrift in 180 Tagen'   AS source_summary,
    to_json([
        {'source_type': 'deterministic', 'reference': p.company_code || '/' || p.year_a || '/' || p.doc_a,
         'value': p.ref_a, 'observed_at': CAST(p.date_a AS VARCHAR), 'agrees': TRUE, 'note': 'Rechnung A'},
        {'source_type': 'deterministic', 'reference': p.company_code || '/' || p.year_b || '/' || p.doc_b,
         'value': p.ref_b, 'observed_at': CAST(p.date_b AS VARCHAR), 'agrees': TRUE, 'note': 'Rechnung B'}
    ])                                                  AS evidence,
    p.amount_doc                                        AS impact_amount,
    p.currency                                          AS impact_currency,
    'Betrag der zweiten Zahlung, keine Gutschrift gefunden'  AS impact_formula,
    NULL                                                AS netted_against,
    to_json([
        {'company_code': p.company_code, 'fiscal_year': p.year_a, 'document_no': p.doc_a, 'line_item': NULL},
        {'company_code': p.company_code, 'fiscal_year': p.year_b, 'document_no': p.doc_b, 'line_item': NULL}
    ])                                                  AS documents,
    to_json({'amount': CAST(p.amount_doc AS VARCHAR), 'currency': p.currency,
             'ref_a': p.ref_a, 'ref_b': p.ref_b})       AS params,
    p.doc_a || '|' || p.doc_b                           AS finding_key
FROM pairs p
LEFT JOIN netted n ON n.key_a = p.key_a AND n.key_b = p.key_b
WHERE n.key_a IS NULL
ORDER BY p.bp_key, p.key_a, p.key_b;
