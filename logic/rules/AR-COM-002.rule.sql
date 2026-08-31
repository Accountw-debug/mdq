/* ---
id: AR-COM-002
version: "1.0"
title: "Zahlungsbedingung im Buchungskreis {company_code} nicht gepflegt"
side: AR
category: completeness
severity: medium
damage_class: 2
default_tier: C
default_action_type: review
requires_tables: [business_partner, bp_company_code, fi_item, payment_terms]
parameters:
  # Ab wie vielen Rechnungen im Buchungskreis eine Mehrheit als Soll taugt. Unter dieser
  # Zahl ist "die Mehrheit der Belege" eine Zufallsaussage: bei zwei Rechnungen genuegte
  # eine einzige. Steht hier und nicht als Zahl im SQL, damit sie sichtbar bleibt (D-107).
  min_invoices: 3
plain_logic: >
  Finding je Buchungskreis, wenn die Zahlungsbedingung (ZTERM) im Debitorenstamm des
  Buchungskreises leer ist. Soll ist die Zahlungsbedingung, die auf **mehr als der Hälfte**
  der Rechnungsbelege dieses Debitors in diesem Buchungskreis steht, sofern es mindestens
  `min_invoices` Rechnungen gibt – dann Stufe B. Gibt es keine solche Mehrheit, keine
  Rechnungen oder zu wenige, entsteht das Finding trotzdem, aber ohne Soll und mit Stufe C:
  ein geratenes Soll wäre schlimmer als keins. CpD-Konten ausgeschlossen.
why: >
  Ohne Zahlungsbedingung im Stammsatz zieht SAP beim Buchen keinen Vorschlag; das Fälligkeitsdatum
  entsteht dann aus dem, was der Erfasser eintippt. Die Folge sind falsche Mahnstufen, ein
  falsches Fälligkeitsbild in der OP-Liste und Skontoabzüge, die niemand vereinbart hat.
if_wrong: >
  Wird eine falsche Bedingung übernommen, verschiebt sich die Fälligkeit aller künftigen
  Rechnungen dieses Kunden – zu früh gemahnt kostet die Beziehung, zu spät gemahnt kostet
  Liquidität. Deshalb Review, keine Massenänderung.
remediation:
  sap_transaction: XD02
  path: "Buchungskreisdaten → Zahlungsverkehr"
  field: ZTERM
  mass_change_eligible: false
tests:
  # Nur Konten, die `testdata/demo_mandant/defects.yaml` namentlich nennt (D-066).
  hits:
    - "C:0000100142"   # DEF-0047: 6 von 6 Rechnungen ZB03 - Mehrheit, Stufe B
    - "C:0000100171"   # DEF-0052: Buchungskreis 2000, Mehrheit
    - "C:0000100196"   # DEF-0062: 10 Rechnungen auf vier Bedingungen - keine Mehrheit, Stufe C
  no_hits:
    - "C:0000100234"   # DEF-0001, Anker F-001: Zahlungsbedingung gepflegt
    - "C:0000100001"   # DEF-0012: Loeschvormerkung, Zahlungsbedingung gepflegt
  edge:
    # Dieselbe Datenlage auf der AP-Seite darf diese Regel nicht liefern (AP-COM-002 gibt
    # es nicht; ein fehlender Rollenfilter faellt hier trotzdem auf).
    - "V:0000200084"   # DEF-0067, Kreditor mit eigenem Stammdatenbefund
--- */
WITH leer AS (
    SELECT c.bp_key, c.company_code, bp.role
    FROM bp_company_code c
    JOIN business_partner bp
      ON bp.bp_key = c.bp_key
    WHERE bp.role = 'CUSTOMER'
      AND bp.is_one_time = FALSE
      AND c.payment_terms IS NULL
),
belege AS (
    SELECT l.bp_key, l.company_code, i.payment_terms AS terms, count(*) AS treffer
    FROM leer l
    JOIN fi_item i
      ON i.bp_key = l.bp_key AND i.company_code = l.company_code
    WHERE i.doc_type IN (${doc_types.AR.invoice})
      AND i.payment_terms IS NOT NULL
    GROUP BY 1, 2, 3
),
gesamt AS (
    SELECT bp_key, company_code, sum(treffer) AS rechnungen, count(*) AS varianten
    FROM belege
    GROUP BY 1, 2
),
spitze AS (
    -- Bei Gleichstand entscheidet der Schluessel, damit die Auswahl reproduzierbar ist
    -- (Regel 9); eine Mehrheit ist ein Gleichstand ohnehin nicht.
    SELECT bp_key, company_code, terms, treffer,
           row_number() OVER (
               PARTITION BY bp_key, company_code ORDER BY treffer DESC, terms
           ) AS rang
    FROM belege
),
befund AS (
    SELECT
        l.bp_key,
        l.role,
        l.company_code,
        coalesce(g.rechnungen, 0)                     AS rechnungen,
        coalesce(g.varianten, 0)                      AS varianten,
        s.terms                                       AS haeufigste,
        coalesce(s.treffer, 0)                        AS haeufigste_treffer,
        coalesce(s.treffer, 0) * 2 > coalesce(g.rechnungen, 0)
            AND coalesce(g.rechnungen, 0) >= ${params.min_invoices}  AS hat_mehrheit
    FROM leer l
    LEFT JOIN gesamt g
      ON g.bp_key = l.bp_key AND g.company_code = l.company_code
    LEFT JOIN spitze s
      ON s.bp_key = l.bp_key AND s.company_code = l.company_code AND s.rang = 1
)
SELECT
    b.bp_key,
    b.role,
    b.company_code,
    'KNB1'                                            AS source_table,
    'ZTERM'                                           AS source_field,
    NULL                                              AS current_value,
    'nicht gepflegt'                                  AS current_display,
    CASE WHEN b.hat_mehrheit THEN b.haeufigste END    AS proposed_value,
    CASE
        WHEN b.hat_mehrheit THEN (
            SELECT max(pt.description) FROM payment_terms pt WHERE pt.terms_key = b.haeufigste
        )
    END                                               AS proposed_display,
    CASE
        WHEN b.hat_mehrheit THEN
            b.haeufigste_treffer::VARCHAR || ' von ' || b.rechnungen::VARCHAR
            || ' Rechnungen im Buchungskreis tragen ' || b.haeufigste
        WHEN b.rechnungen = 0 THEN
            'Keine Rechnung im Buchungskreis – kein Soll ableitbar'
        ELSE
            'Kein Soll ableitbar: ' || b.rechnungen::VARCHAR || ' Rechnungen verteilen sich auf '
            || b.varianten::VARCHAR || ' Zahlungsbedingungen ohne Mehrheit'
    END                                               AS source_summary,
    -- Stufe B nur mit Mehrheit: beobachtetes Verhalten ist eine starke Quelle, eine
    -- Minderheit ist keine (CONCEPT §4). Ohne Mehrheit Stufe C ohne Soll.
    CASE WHEN b.hat_mehrheit THEN 'B' ELSE 'C' END    AS tier,
    to_json([{
        'source_type':    'invoice',
        'reference':      'Rechnungsbelege im Buchungskreis ' || b.company_code,
        'reference_kind': 'document',
        'value':          coalesce(b.haeufigste, '–'),
        'observed_at':    NULL,
        'agrees':         b.hat_mehrheit,
        'note':           b.haeufigste_treffer::VARCHAR || ' von ' || b.rechnungen::VARCHAR
                          || ' Rechnungen; im Buchungskreis '
                          || CASE WHEN b.varianten = 1 THEN 'nur diese eine Bedingung'
                                  ELSE b.varianten::VARCHAR || ' verschiedene Bedingungen' END
    }])                                               AS evidence,
    to_json({'company_code': b.company_code})         AS params
FROM befund b
ORDER BY b.bp_key, b.company_code;
