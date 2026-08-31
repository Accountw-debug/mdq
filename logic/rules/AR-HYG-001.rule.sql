/* ---
id: AR-HYG-001
version: "1.0"
title: "Löschkandidat: kein Posten im Postenfenster, angelegt vor {window_from}"
side: AR
category: hygiene
severity: low
damage_class: 3
default_tier: decision
default_action_type: decision
requires_tables: [business_partner, bp_relevance, fi_item]
plain_logic: >
  Finding, wenn ein Debitor (kein CpD) im gesamten Postenfenster keinen einzigen Posten
  hat, vor Beginn des Fensters angelegt wurde und keine offenen Posten trägt (D-049).
  Der Fensterbeginn kommt vom Lauf, nicht aus der Regel: aus dem Scope, sonst aus dem
  frühesten Buchungsdatum der geladenen Posten (D-110). Konten, die **im** Fenster
  angelegt wurden und noch nichts gebucht haben, sind Neuanlagen und gehören zu
  AR-HYG-002 – ohne Anlagedatum gilt ein Konto als vor dem Fenster angelegt (D-086).
  Keine Empfehlung, nur Optionen: ob ein stillgelegtes Konto gelöscht, archiviert oder
  behalten wird, hängt an Aufbewahrungsfristen und Kundenbeziehung, nicht an den Daten.
why: >
  Karteileichen im Debitorenstamm kosten in jeder Migration Geld (Konvertierung, Test,
  Nacharbeit), verwässern jede Dublettenprüfung und jede Auswertung, und sie sind der
  bequemste Ort für eine unbemerkte Bankdatenänderung: auf einem Konto, das niemand
  ansieht, fällt auch niemandem etwas auf.
if_wrong: >
  Ein zu früh gelöschtes Konto nimmt die Historie mit – Aufbewahrungsfristen (§ 147 AO,
  zehn Jahre) gelten unabhängig davon, ob noch gebucht wird. Deshalb nie automatisch,
  sondern Löschvormerkung setzen und die Frist abwarten.
remediation:
  sap_transaction: XD06
  path: "Löschvormerkung setzen, Archivierung über SARA"
  field: LOEVM
  mass_change_eligible: false
  steps:
    - "Aufbewahrungsfrist prüfen (letzter Beleg, § 147 AO)"
    - "Option A: Löschvormerkung setzen, Konto zur Archivierung anmelden"
    - "Option B: Konto behalten, wenn die Kundenbeziehung ruht, aber bestehen soll"
    - "Option C: Buchungssperre setzen, ohne zu löschen"
tests:
  # Nur Konten, die `testdata/demo_mandant/defects.yaml` namentlich nennt (D-066).
  hits:
    - "C:0000100003"   # DEF-0069: kein Posten im Fenster, angelegt davor
    - "C:0000100018"   # DEF-0069
    - "C:0000100034"   # DEF-0069
  no_hits:
    - "C:0000100234"   # DEF-0001, Anker F-001: aktives Konto mit Posten
    - "C:0000100001"   # DEF-0012: Loeschvormerkung, aber Posten vorhanden
  edge:
    # Dieselbe Datenlage auf der AP-Seite: diese Regel darf sie nicht liefern, das ist
    # AP-HYG-001 (Aufgabe 7).
    - "V:0000200084"   # DEF-0070 betrifft dieselbe Seite; Kreditor mit Stammdatenbefund
--- */
SELECT
    bp.bp_key,
    bp.role,
    NULL                                          AS company_code,
    'KNA1'                                        AS source_table,
    'ERDAT'                                       AS source_field,
    bp.created_on::VARCHAR                        AS current_value,
    'kein Posten im Postenfenster, keine offenen Posten'  AS current_display,
    NULL                                          AS proposed_value,
    NULL                                          AS proposed_display,
    'Kein Posten seit Fensterbeginn ' || ${scope.item_window_from}::VARCHAR
        || '; Anlage davor; offene Posten 0,00 ' || r.currency  AS source_summary,
    to_json([
        {'label': 'Löschvormerkung setzen und archivieren',
         'consequence': 'Konto verschwindet aus Auswahllisten; Historie bleibt bis zum Archivlauf'},
        {'label': 'Konto behalten',
         'consequence': 'Ruhende Kundenbeziehung bleibt bebuchbar; Karteileiche bleibt in jeder Auswertung'},
        {'label': 'Nur Buchungssperre setzen',
         'consequence': 'Keine neuen Buchungen, Stammsatz bleibt für Auswertung und Historie erhalten'}
    ])                                            AS options,
    to_json([{
        'source_type':    'deterministic',
        'reference':      'fi_item',
        'reference_kind': 'document',
        'value':          'kein Posten im Postenfenster',
        'observed_at':    NULL,
        'agrees':         TRUE,
        'note':           'Letzte Aktivität: keine; Anlagedatum vor Fensterbeginn'
    }])                                           AS evidence,
    to_json({'window_from': ${scope.item_window_from}::VARCHAR})  AS params
FROM business_partner bp
JOIN bp_relevance r
  ON r.bp_key = bp.bp_key
WHERE bp.role = 'CUSTOMER'
  AND bp.is_one_time = FALSE
  -- Kein Posten im gesamten Postenfenster: die geladenen Posten *sind* das Fenster
  AND NOT EXISTS (SELECT 1 FROM fi_item i WHERE i.bp_key = bp.bp_key)
  AND r.open_items_local = 0
  -- Angelegt vor Fensterbeginn (D-049). Ohne Anlagedatum gilt das Konto als aelter als
  -- das Fenster (D-086) - "nie bebucht" ist die staerkere Behauptung und braucht ein Datum.
  AND (bp.created_on IS NULL OR bp.created_on < ${scope.item_window_from})
ORDER BY bp.bp_key;
