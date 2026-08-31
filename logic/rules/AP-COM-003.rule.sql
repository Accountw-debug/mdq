/* ---
id: AP-COM-003
version: "1.0"
title: "Prüfung auf doppelte Rechnung nicht gesetzt (Buchungskreis {company_code})"
side: AP
category: completeness
severity: high
damage_class: 3
default_tier: A
default_action_type: mass_change
requires_tables: [business_partner, bp_company_code]
plain_logic: >
  Finding je Kreditor und Buchungskreis (kein CpD), in dem das Kennzeichen „Prüfung auf
  doppelte Rechnung" (LFB1-REPRF) nicht gesetzt ist. REPRF ist ein Ankreuzfeld: SAP
  schreibt es als 'X' oder lässt es leer, das Staging macht aus dem Initialwert NULL
  (D-032/D-033). Leer und ausdrücklich falsch bedeuten hier dasselbe – nicht gesetzt –,
  deshalb prüft die Regel `IS NOT TRUE` und nicht `IS NULL`. Soll ist das gesetzte
  Kennzeichen; die Quellenlage nennt, wie viele Buchungskreis-Sätze des Mandanten es
  bereits tragen. **Erste Regel mit Stufe A und Massenänderung:** das ist hier tragbar,
  weil das Kennzeichen keinen Wert ändert, sondern eine Prüfung einschaltet – es ist
  reversibel, Schadensklasse 3, und es gibt kein Feld, dessen Inhalt verloren gehen
  könnte. Schadensklasse 1 bliebe davon unberührt (Regel 11).
why: >
  Ohne dieses Kennzeichen warnt SAP bei der Rechnungserfassung nicht mehr, wenn zu
  demselben Kreditor eine Rechnung mit gleicher Referenz, gleichem Betrag und gleichem
  Datum schon gebucht ist. Die Doppelerfassung fällt dann erst im Zahllauf auf – oder gar
  nicht. Genau diese Lücke misst AP-LEA-001 auf der Belegseite: dort steht der Schaden in
  Euro, hier steht seine Ursache im Stammsatz.
if_wrong: >
  Ein zu Unrecht gesetztes Kennzeichen kostet nichts: es blockiert keine Buchung, sondern
  zeigt beim Erfassen eine Warnung, die sich übergehen lässt. Bei Kreditoren mit bewusst
  wiederkehrenden Referenznummern (Abschlagsrechnungen, Sammelabrechnungen) fällt dabei
  Nacharbeit an – ein Grund, die Massenänderung anzukündigen, aber keiner, sie zu lassen.
  Rücknahme ist derselbe Handgriff.
remediation:
  sap_transaction: XK02
  path: "Buchungskreisdaten → Zahlungsverkehr → Prüfung doppelte Rechnung"
  field: REPRF
  mass_change_eligible: true
  steps:
    - "Massenänderung über XK99 (Objekt Kreditor, Feld LFB1-REPRF) auf die betroffenen Buchungskreis-Sätze"
    - "Kreditoren mit wiederkehrenden Referenznummern vorab mit der Kreditorenbuchhaltung abstimmen"
    - "Nach der Änderung an einem Rechnungseingang stichprobenweise prüfen, dass die Warnung erscheint"
tests:
  # Nur Konten, die `testdata/demo_mandant/defects.yaml` namentlich nennt (D-066).
  hits:
    - "V:0000200084"   # DEF-0067: REPRF leer, Buchungskreis 1000
    - "V:0000200088"   # DEF-0067: REPRF leer, Buchungskreis 2000
    - "V:0000200148"   # DEF-0067: REPRF leer, Buchungskreis 2000
  no_hits:
    - "V:0000200845"   # DEF-0004, Anker F-004: REPRF gesetzt
    - "V:0000200117"   # DEF-0005, Anker F-005: REPRF gesetzt
  edge:
    # REPRF gibt es nur im Kreditoren-Buchungskreissatz (LFB1); KNB1 kennt das Feld nicht.
    # Diese Regel darf deshalb nie ein Debitorenkonto liefern - der Rollenfilter haelt das,
    # auch wenn der Join es allein schon taete.
    - "C:0000100234"   # DEF-0001, Anker F-001
--- */
WITH bestand AS (
    -- Wie viele Buchungskreis-Saetze des Mandanten das Kennzeichen tragen. Das ist die
    -- Quellenlage des Solls: nicht eine Regel von aussen, sondern die eigene Praxis.
    SELECT
        count(*)                                                  AS saetze,
        count(*) FILTER (WHERE c.double_invoice_check IS TRUE)     AS gesetzt
    FROM bp_company_code c
    JOIN business_partner bp
      ON bp.bp_key = c.bp_key
    WHERE bp.role = 'VENDOR'
      AND bp.is_one_time = FALSE
)
SELECT
    c.bp_key,
    bp.role,
    c.company_code,
    'LFB1'                                        AS source_table,
    'REPRF'                                       AS source_field,
    -- Das Ankreuzfeld ist leer; ein Ist-Wert waere hier eine Erfindung
    NULL                                          AS current_value,
    'nicht gesetzt'                               AS current_display,
    'X'                                           AS proposed_value,
    'Prüfung auf doppelte Rechnung einschalten'   AS proposed_display,
    b.gesetzt::VARCHAR || ' von ' || b.saetze::VARCHAR
        || ' Kreditor-Buchungskreissätzen im Mandanten tragen das Kennzeichen bereits'
                                                  AS source_summary,
    to_json([{
        'source_type':    'deterministic',
        'reference':      'LFB1 ' || c.company_code,
        'reference_kind': 'master_field',
        'value':          'nicht gesetzt',
        'observed_at':    NULL,
        'agrees':         FALSE,
        'note':           b.gesetzt::VARCHAR || ' von ' || b.saetze::VARCHAR
                          || ' Buchungskreissätzen tragen das Kennzeichen'
    }])                                           AS evidence,
    to_json({'company_code': c.company_code})     AS params
FROM bp_company_code c
JOIN business_partner bp
  ON bp.bp_key = c.bp_key
CROSS JOIN bestand b
WHERE bp.role = 'VENDOR'
  AND bp.is_one_time = FALSE
  -- Leer (SAP-Initialwert, im Staging NULL) und ausdrueckliches FALSE heissen beide
  -- "nicht gesetzt"; IS NULL allein wuerde das zweite uebersehen.
  AND c.double_invoice_check IS NOT TRUE
ORDER BY c.bp_key, c.company_code;
