/* ---
id: AR-VAL-005
version: "1.0"
title: "Platzhalter statt echtem Wert im Feld {feld}"
side: AR
category: validity
severity: medium
damage_class: 3
default_tier: C
default_action_type: review
requires_tables: [business_partner]
plain_logic: >
  Finding, wenn Name (NAME1) oder Ort (ORT01) eines Debitors (kein CpD) einen Begriff aus
  `logic/dictionaries/placeholder_terms.yaml` **als ganzes Wort** enthält – "Test GmbH",
  "unbekannt", "xxx", "Dummy Konto". Groß- und Kleinschreibung spielt keine Rolle, SAP-Namen
  kommen oft durchgehend in Großbuchstaben. Bewusst keine Präfixregel `Test*`: "Testo SE"
  ist ein realer Hersteller; Zusammensetzungen wie "Testkunde" stehen ausgeschrieben im
  Wörterbuch. Trifft es Name und Ort zugleich, entsteht **ein** Finding und der Name wird
  genannt – er wiegt schwerer. **Kein `proposed`**: der richtige Name steht nirgends in den
  Daten, und ein Vorschlag, der nur das erklärt, sieht aus wie ein leerer (D-186); das
  Vorgehen steht unter `remediation`.
why: >
  Ein Platzhaltername macht das Konto in jeder Auswertung, Mahnung und Rechnung unbrauchbar
  und ist in der Dublettenprüfung ein Blindgänger – "Test GmbH" gleicht sich mit nichts ab.
  Meist ist es ein Konto, das für einen Einzelfall angelegt und nie aufgeräumt wurde;
  es bleibt bebuchbar und fällt niemandem auf.
if_wrong: >
  Wird irgendein plausibler Name eingetragen, ist der Stammsatz formal sauber und zeigt auf
  einen Kunden, den es so nicht gibt. Der richtige Wert kommt aus dem Beleg oder dem Auftrag,
  nicht aus dem System – deshalb Review, keine Massenänderung.
remediation:
  sap_transaction: XD02
  path: "Adresse → Name / Ort"
  field: NAME1 / ORT01
  mass_change_eligible: false
  steps:
    - "Zugehörigen Beleg oder Auftrag suchen (ZUONR, SGTXT, Bestellung) und den echten Namen übernehmen"
    - "Findet sich kein Beleg: Konto sperren statt umbenennen – ein erfundener Name ist schlimmer als ein erkennbarer Platzhalter"
tests:
  # Nur Konten, die `testdata/demo_mandant/defects.yaml` namentlich nennt (D-066).
  hits:
    - "C:0000100214"   # DEF-0068: "Test GmbH"
    - "C:0000100216"   # DEF-0068: "unbekannt"
    - "C:0000100220"   # DEF-0068: "xxx"
  no_hits:
    - "C:0000100234"   # DEF-0001, Anker F-001: echter Firmenname
    - "C:0000100010"   # DEF-0150: CpD-Konto mit echtem Namen
  edge:
    # Platzhalter als Teil eines laengeren Namens: trifft nur, weil "testkunde" und
    # "testfirma" ausgeschrieben im Woerterbuch stehen - eine Praefixregel gibt es nicht.
    - "C:0000100215"   # DEF-0068: "Testkunde 2"
    - "C:0000100221"   # DEF-0068: "Testfirma Nord"
--- */
WITH geprueft AS (
    SELECT
        bp.bp_key,
        bp.role,
        bp.name1,
        bp.city,
        -- Der Text wird in Grenzzeichen eingefasst, damit ein Begriff auch am Anfang und
        -- am Ende des Feldes seine Wortgrenze hat (RE2 kennt keine Lookarounds).
        regexp_matches('#' || lower(coalesce(bp.name1, '')) || '#',
                       ${placeholder_terms.pattern})              AS name_trifft,
        regexp_matches('#' || lower(coalesce(bp.city, '')) || '#',
                       ${placeholder_terms.pattern})              AS ort_trifft,
        regexp_extract('#' || lower(coalesce(bp.name1, '')) || '#',
                       ${placeholder_terms.pattern})              AS name_begriff,
        regexp_extract('#' || lower(coalesce(bp.city, '')) || '#',
                       ${placeholder_terms.pattern})              AS ort_begriff
    FROM business_partner bp
    WHERE bp.role = 'CUSTOMER'
      AND bp.is_one_time = FALSE
)
SELECT
    g.bp_key,
    g.role,
    NULL                                              AS company_code,
    'KNA1'                                            AS source_table,
    -- Name und Ort zugleich: ein Finding, und der Name wird genannt. Zwei Findings fuer
    -- dasselbe leere Konto waeren zwei Zeilen ueber einen Sachverhalt.
    CASE WHEN g.name_trifft THEN 'NAME1' ELSE 'ORT01' END          AS source_field,
    CASE WHEN g.name_trifft THEN g.name1 ELSE g.city END           AS current_value,
    'Platzhalter „'
        || trim(CASE WHEN g.name_trifft THEN g.name_begriff ELSE g.ort_begriff END,
                '#.,;:/-_ ')
        || '" als eigenes Wort'                                    AS current_display,
    -- Kein Soll und deshalb kein proposed (D-186): das Vorgehen steht unter remediation.
    NULL                                              AS proposed_value,
    NULL                                              AS proposed_display,
    NULL                                              AS source_summary,
    to_json([{
        'source_type':    'deterministic',
        'reference':      'placeholder_terms.yaml',
        'reference_kind': 'policy',
        'value':          trim(CASE WHEN g.name_trifft THEN g.name_begriff
                                    ELSE g.ort_begriff END, '#.,;:/-_ '),
        'observed_at':    NULL,
        'agrees':         FALSE,
        'note':           'Treffer als ganzes Wort, ohne Ruecksicht auf Gross-/Kleinschreibung'
    }])                                               AS evidence,
    to_json({'feld': CASE WHEN g.name_trifft THEN 'NAME1' ELSE 'ORT01' END})  AS params
FROM geprueft g
WHERE g.name_trifft OR g.ort_trifft
ORDER BY g.bp_key;
