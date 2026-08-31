/* ---
id: AR-LEA-001
version: "1.0"
title: "Unapplied Cash: {amount} seit {days} Tagen ohne Rechnungsbezug"
side: AR
category: leakage
severity: medium
damage_class: 3
default_tier: B
default_action_type: review
requires_tables: [business_partner, fi_item]
parameters:
  # Ab wann eine unzugeordnete Zahlung ein Befund ist, in Tagen vor dem Datenstand.
  # Eine Anzahl, kein Betrag - deshalb eine Zahl und keine Zeichenkette (D-194).
  min_age_days: 30
plain_logic: >
  Finding je Beleg, wenn ein Zahlungseingang eines Debitors offen steht, keinen
  Rechnungsbezug trägt und am Datenstand älter als `${params.min_age_days}` Tage ist.
  Ohne Rechnungsbezug heißt: Referenz (XBLNR) leer, Zuordnung (ZUONR) leer, kein
  Rechnungsbezugsbeleg (REBZG) und kein Ausgleich (AUGDT/AUGBL). Die Belegart kommt aus
  dem Wörterbuch (`${doc_types.AR.payment}`), nicht als Liste aus dem SQL (D-084/D-091),
  und die Richtung aus dem Soll-/Haben-Kennzeichen: ein Zahlungseingang ist beim Debitor
  Haben.
  **Sonderhauptbuchvorgänge bleiben außen vor** (`special_gl IS NULL`): eine Anzahlung
  (UMSKZ A) ist gewollt ohne Rechnungsbezug, und ohne diesen Ausschluss meldete die Regel
  auf einem echten Mandanten jede Anzahlung. Im Demo-Mandanten ist UMSKZ durchgehend
  leer – die Klausel ist damit **ungetestet** und steht hier als benannte Lücke, nicht in
  einer Fußnote (Muster D-191).
  Der Stichtag kommt aus dem Lauf (`${scope.data_as_of}`), nie aus `current_date`:
  derselbe Input muss dieselben Findings liefern (Regel 9, D-193).
  **Ein Finding je Beleg**, deshalb trägt die Regel den `finding_key` – die Belegnummer.
  Ein Konto kann mehrere unzugeordnete Zahlungen tragen; ohne den Schlüssel kollidierten
  ihre `finding_id`s, weil `bp_key`, Feld und Ist bei allen gleich sind.
  **Keine Euro-Wirkung:** Unapplied Cash ist gebundenes, nicht verlorenes Geld. Der
  Betrag steht im Ist und in `entity.documents`; als `impact_eur` gezählt würde er in
  jeder Summe als Schaden gelesen, und das ist er nicht (D-192).
  CpD-Konten bleiben drin: eine unzugeordnete Zahlung auf einem Sammelkonto ist genauso
  echt wie auf einem geführten Konto – der CpD-Ausschluss gilt Stammdatenregeln, nicht
  Belegregeln.
why: >
  Geld ist auf dem Konto, aber keiner Forderung zugeordnet. Die Folgen laufen in beide
  Richtungen: der Kunde wird für eine Rechnung gemahnt, die er längst bezahlt hat, und
  die Forderung steht in der Altersstruktur als überfällig, obwohl sie es nicht ist.
  Kreditlimit und Mahnstufe arbeiten mit falschen Zahlen, und je länger die Zahlung
  liegt, desto schwerer ist noch nachzuvollziehen, wofür sie kam.
if_wrong: >
  Wird die Zahlung der falschen Rechnung zugeordnet, ist eine bezahlte Forderung
  ausgeglichen und eine offene bleibt liegen – der Fehler wandert nur weiter und fällt
  erst bei der nächsten Mahnung auf. Deshalb Stufe B und Review: die Zuordnung wird
  vorgeschlagen, nicht gebucht. Findet sich keine passende Rechnung, ist die Rückzahlung
  richtig und nicht das Stehenlassen.
remediation:
  sap_transaction: F-32
  path: "Debitor ausgleichen: Zahlung und offene Rechnung(en) auswählen"
  field: null
  mass_change_eligible: false
  steps:
    - "Zahlungsavis oder Kontoauszug zum Beleg heraussuchen und den Verwendungszweck lesen"
    - "Offene Rechnungen des Kontos gegenüberstellen – Betrag und Zeitpunkt eingrenzen die Kandidaten"
    - "Passt eine: in F-32 ausgleichen. Passt keine: Rückzahlung veranlassen, nicht weiter stehen lassen"
    - "Wiederholt sich das Muster beim selben Kunden, den Verwendungszweck im Zahlungsavis mit ihm klären"
tests:
  # Nur Konten, die `testdata/demo_mandant/defects.yaml` namentlich nennt (D-066).
  hits:
    - "C:0000100293"   # DEF-0119: Akonto 4.200,00 vom 15.06.2026
    - "C:0000100298"   # DEF-0119: Akonto 9.300,00 vom 01.07.2026, BUKRS 2000
    - "C:0000100302"   # DEF-0119: Akonto 2.640,00 vom 17.03.2026
  no_hits:
    - "C:0000100234"   # DEF-0001, Anker F-001: keine unzugeordnete Zahlung
    - "C:0000100280"   # DEF-0106: Skonto innerhalb der Frist gezogen, Zahlung ausgeglichen
  edge:
    # Zahlungsausgaenge an Kreditoren haben dieselbe Form (offen, ohne Bezug) und
    # gehoeren nicht hierher; der Rollenfilter haelt das.
    - "V:0000200117"   # DEF-0005, Anker F-005: Kreditor mit offenen Posten
    # Ungetestet, benannt: der Ausschluss der Sonderhauptbuchvorgaenge. Der
    # Demo-Mandant fuehrt kein UMSKZ; sobald ein Defekt eine Anzahlung setzt, gehoert
    # sein Konto hierher - es darf **kein** Finding liefern.
--- */
WITH akonto AS (
    SELECT
        i.bp_key,
        i.company_code,
        i.fiscal_year,
        i.document_no,
        i.line_item,
        i.posting_date,
        i.document_date,
        i.amount_doc,
        i.currency,
        date_diff('day', i.posting_date, ${scope.data_as_of}) AS tage
    FROM fi_item i
    JOIN business_partner bp
      ON bp.bp_key = i.bp_key
    WHERE bp.role = 'CUSTOMER'
      -- Zahlungseingang: beim Debitor Haben, Belegart aus dem Woerterbuch (D-091)
      AND i.debit_credit = 'H'
      AND i.doc_type IN (${doc_types.AR.payment})
      AND i.is_open = TRUE
      -- Anzahlungen und andere Sonderhauptbuchvorgaenge sind gewollt ohne Bezug
      AND i.special_gl IS NULL
      -- Ohne Rechnungsbezug: weder Referenz noch Zuordnung noch Bezugsbeleg
      AND i.reference_norm IS NULL
      AND i.assignment IS NULL
      AND i.invoice_ref_doc IS NULL
      -- Kein Ausgleich: die Zahlung liegt wirklich noch da
      AND i.clearing_date IS NULL
      AND i.clearing_doc IS NULL
      AND date_diff('day', i.posting_date, ${scope.data_as_of}) > ${params.min_age_days}
),
-- Die offenen Rechnungen desselben Kontos im selben Buchungskreis: sie sind die
-- Kandidaten fuer die Zuordnung und entscheiden, ob der Handlungssatz "ausgleichen"
-- oder "zurueckzahlen" lautet.
kandidat AS (
    SELECT
        i.bp_key,
        i.company_code,
        count(*)                    AS rechnungen,
        sum(i.amount_doc)           AS summe,
        min(i.currency)             AS currency
    FROM fi_item i
    WHERE i.debit_credit = 'S'
      AND i.doc_type IN (${doc_types.AR.invoice})
      AND i.is_open = TRUE
    GROUP BY i.bp_key, i.company_code
)
SELECT
    a.bp_key,
    'CUSTOMER'                                    AS role,
    a.company_code,
    'BSID'                                        AS source_table,
    'XBLNR'                                       AS source_field,
    -- Das Feld ist leer - genau das ist der Befund (dieselbe Form wie AR-COM-002).
    NULL                                          AS current_value,
    'Zahlungseingang über ' || mdq_money(a.amount_doc, a.currency)
        || ' vom ' || a.posting_date::VARCHAR
        || ', seit ' || a.tage::VARCHAR || ' Tagen ohne Rechnungsbezug und ohne Ausgleich'
                                                  AS current_display,
    -- Stufe B verlangt ein Soll; welche Rechnung gemeint ist, sagen die Daten nicht -
    -- das Soll ist deshalb eine Handlung und kein Wert (D-186, wie AP-LEA-001).
    NULL                                          AS proposed_value,
    CASE WHEN coalesce(k.rechnungen, 0) > 0
         THEN 'Zahlung einer offenen Rechnung zuordnen (F-32)'
         ELSE 'Keine offene Rechnung auf dem Konto – Rückzahlung veranlassen'
    END                                           AS proposed_display,
    'Beleg ' || a.document_no || ': XBLNR, ZUONR und REBZG leer, kein Ausgleichsbeleg, '
        || a.tage::VARCHAR || ' Tage alt; '
        || CASE WHEN coalesce(k.rechnungen, 0) = 0 THEN 'keine offene Rechnung im Buchungskreis'
                WHEN k.rechnungen = 1 THEN 'eine offene Rechnung über ' || mdq_money(k.summe, k.currency)
                ELSE k.rechnungen::VARCHAR || ' offene Rechnungen über '
                     || mdq_money(k.summe, k.currency) END
                                                  AS source_summary,
    to_json([
        {
            'source_type':    'deterministic',
            'reference':      a.company_code || '/' || a.fiscal_year || '/' || a.document_no,
            'reference_kind': 'document',
            'value':          mdq_money(a.amount_doc, a.currency),
            'observed_at':    a.posting_date::VARCHAR,
            'agrees':         TRUE,
            'note':           'Zahlungseingang, offen und ohne Rechnungsbezug'
        },
        {
            'source_type':    'deterministic',
            'reference':      'BSID ' || a.company_code,
            'reference_kind': 'document',
            'value':          CASE WHEN coalesce(k.rechnungen, 0) = 0 THEN 'keine offene Rechnung'
                                   ELSE k.rechnungen::VARCHAR || ' offene Rechnungen über '
                                        || mdq_money(k.summe, k.currency) END,
            'observed_at':    ${scope.data_as_of}::VARCHAR,
            'agrees':         coalesce(k.rechnungen, 0) > 0,
            'note':           'Kandidaten für die Zuordnung im selben Buchungskreis'
        }
    ])                                            AS evidence,
    -- Kein impact_eur: Unapplied Cash ist gebundenes, nicht verlorenes Geld (D-192).
    to_json([{
        'company_code':  a.company_code,
        'fiscal_year':   a.fiscal_year,
        'document_no':   a.document_no,
        'line_item':     a.line_item,
        'reference':     NULL,
        'document_date': a.document_date::VARCHAR,
        'cleared_on':    NULL,
        'amount':        a.amount_doc::VARCHAR,
        'currency':      a.currency
    }])                                           AS documents,
    to_json({
        'amount': mdq_money(a.amount_doc, a.currency),
        'days':   a.tage
    })                                            AS params,
    -- Ein Konto kann mehrere unzugeordnete Zahlungen tragen; ohne die Belegnummer
    -- kollidierten ihre finding_id (bp_key, Feld und Ist sind bei allen gleich).
    a.document_no                                 AS finding_key
FROM akonto a
LEFT JOIN kandidat k
  ON k.bp_key = a.bp_key
 AND k.company_code = a.company_code
ORDER BY a.bp_key, a.company_code, a.document_no;
