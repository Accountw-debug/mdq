/* ---
id: CROSS-DUP-001
version: "1.0"
title: "Kunde und Lieferant mit derselben {match_label} ({match_value})"
side: CROSS
category: duplicate
severity: medium
damage_class: 2
default_tier: B
default_action_type: review
requires_tables: [business_partner, bp_tax_id, bp_bank_account, bp_relevance]
plain_logic: >
  Finding, wenn derselbe Geschäftspartner zugleich als Debitor und als Kreditor geführt
  wird (kein CpD). Als Beleg dafür gilt eine deterministische Übereinstimmung – kein
  Fuzzy: **dieselbe normalisierte USt-IdNr.** oder **dieselbe normalisierte IBAN**. Beide
  Kriterien zählen einzeln; treffen beide zu, steht das Finding trotzdem nur einmal da
  und nennt beide.
  **Ein Finding je Debitor, nicht je Paar:** der Anker sitzt fest auf dem Debitorenkonto
  (D-052 – nicht auf dem kleinsten `bp_key`, auch wenn das hier zufällig dasselbe ergäbe;
  welche Seite führt, ist eine fachliche Festlegung und keine Folge der Sortierung). Die
  gefundenen Kreditorenkonten stehen in `related_bp_keys`, und `entity.records` trägt je
  beteiligtem Konto die Vergleichsfelder (D-069 Punkt 3, Form nach D-190). Der Anker
  steht mit in `records`, sonst fehlte die Zeile, gegen die verglichen wird.
  `iban_masked` steht in `records` nur, wenn die Bankverbindung das Trefferkriterium war
  – dann ist sie für alle Konten dieselbe und eindeutig; sonst bliebe offen, welche der
  mehreren Bankverbindungen eines Kontos gemeint ist (dieselbe Überlegung wie bei
  `payment_terms` in D-190). Schadensklasse 2, aber Bankdaten kommen vor: die IBAN steht
  ausschließlich maskiert im Finding (Regel 8, D-105).
  Kein Zusammenführen: ein Konto, das legitim beides ist, bleibt beides. Das Soll ist
  deshalb ein Vorgehen – Verrechnung prüfen –, kein führendes Konto.
why: >
  Forderung und Verbindlichkeit gegenüber demselben Geschäftspartner stehen unverbunden
  nebeneinander: es wird bezahlt, obwohl gleichzeitig eine Forderung offen ist, und
  gemahnt, obwohl man dem Partner Geld schuldet. Beides kostet Liquidität und Ansehen.
  Fällt der Partner aus, ist die Forderung ungesichert, obwohl eine Aufrechnungslage
  bestanden hätte. In der S/4-Konvertierung entstehen aus den beiden Konten außerdem
  zwei Business Partner, wo einer mit zwei Rollen richtig wäre.
if_wrong: >
  Wird eine Verrechnung gebucht, wo keine Aufrechnungslage besteht – verschiedene
  Konzerngesellschaften mit gemeinsamer Steuernummer, ein Factoring- oder Treuhandkonto
  hinter beiden Seiten –, sind Forderung und Verbindlichkeit falsch ausgeglichen und
  müssen zurückgebucht werden. Deshalb Stufe B und Review: die Verbindung wird
  vorgeschlagen, die Aufrechnung nicht automatisch gebucht. Und deshalb nie
  zusammenführen: ein Geschäftspartner darf zu Recht Kunde und Lieferant sein.
remediation:
  sap_transaction: XD02 / XK02
  path: "Steuerung → Verrechnungskennzeichen (Debitor/Kreditor gegenseitig eintragen)"
  field: null
  mass_change_eligible: false
  steps:
    - "Prüfen, ob es derselbe Rechtsträger ist (Handelsregister, Adresse, USt-IdNr.) – oder nur dieselbe Steuernummer im Konzern"
    - "Bei Identität: im Debitor den Kreditor und im Kreditor den Debitor eintragen und die Verrechnung freigeben"
    - "Offene Posten beider Seiten gegenüberstellen und die Aufrechnung mit dem Partner abstimmen"
    - "Konten nicht zusammenführen – ein Geschäftspartner darf beide Rollen haben"
tests:
  # Nur Konten, die `testdata/demo_mandant/defects.yaml` namentlich nennt (D-066).
  hits:
    - "C:0000100285"   # DEF-0114: gleiche USt-IdNr. wie V:0000200206
    - "C:0000100287"   # DEF-0116
    - "C:0000100289"   # DEF-0118
  no_hits:
    # Die Kreditorenseite der Paare: sie steht im Finding des Debitors, traegt aber
    # keines eigenes - ein Finding je Debitor, nicht je Paar (D-052).
    - "V:0000200206"   # DEF-0114
    - "V:0000200220"   # DEF-0118
    - "C:0000100234"   # DEF-0001, Anker F-001: USt-IdNr. nur auf der Debitorenseite
  edge:
    # Zwei Konten *derselben* Seite mit gleicher USt-IdNr. gehoeren zu AR-DUP-001 bzw.
    # AP-DUP-001 (Sprint 4), nie hierher; der Rollenfilter haelt das.
    - "C:0000100987"   # DEF-0002, Anker F-002: Debitoren-Dublette
    # Testluecke, benannt statt verschwiegen (Muster D-191): das IBAN-Kriterium ist im
    # Demo-Mandanten **nicht ausgeuebt** - kein Debitor teilt eine Bankverbindung mit
    # einem Kreditor (gemessen: 1.672 Debitoren- und 1.443 Kreditoren-IBAN, keine
    # Ueberschneidung). Belegt ist damit nur die USt-IdNr.-Haelfte der Regel. Sobald ein
    # Defekt vom Typ "customer_is_vendor" ueber die Bankverbindung dazukommt, gehoert
    # sein Debitorenkonto zu `hits`.
    - "V:0000200845"   # DEF-0004, Anker F-004: IBAN nur einmal vergeben
--- */
WITH konto AS (
    -- CpD-Konten bleiben aussen vor: ein Sammelkonto traegt fremde Steuer- und
    -- Bankdaten, und jede Uebereinstimmung darauf ist ein Artefakt (README "Regeln fuer
    -- Regeln").
    SELECT bp_key, role
    FROM business_partner
    WHERE is_one_time = FALSE
),
-- Kriterium 1: dieselbe normalisierte USt-IdNr. auf beiden Seiten.
ust AS (
    SELECT
        k.bp_key                        AS customer_key,
        v.bp_key                        AS vendor_key,
        'USt-IdNr.'                     AS kriterium,
        'STCEG'                         AS feld,
        tk.value_norm                   AS wert,
        'KNA1-STCEG / LFA1-STCEG'       AS referenz
    FROM bp_tax_id tk
    JOIN konto k        ON k.bp_key = tk.bp_key AND k.role = 'CUSTOMER'
    JOIN bp_tax_id tv   ON tv.value_norm = tk.value_norm AND tv.tax_id_type = 'VAT'
    JOIN konto v        ON v.bp_key = tv.bp_key AND v.role = 'VENDOR'
    WHERE tk.tax_id_type = 'VAT'
),
-- Kriterium 2: dieselbe normalisierte IBAN auf beiden Seiten. Schadensklasse 1 beruehrt:
-- die IBAN verlaesst diese Regel nur maskiert (Regel 8, Maske nach
-- logic/finding.schema.json $defs.iban_masked).
bank AS (
    SELECT
        k.bp_key                        AS customer_key,
        v.bp_key                        AS vendor_key,
        'Bankverbindung'                AS kriterium,
        'IBAN'                          AS feld,
        substr(bk.iban_norm, 1, 4) || ' … ' || substr(bk.iban_norm, -4) AS wert,
        'TIBAN BANKL ' || coalesce(bk.bank_key, '–')                    AS referenz
    FROM bp_bank_account bk
    JOIN konto k              ON k.bp_key = bk.bp_key AND k.role = 'CUSTOMER'
    JOIN bp_bank_account bv   ON bv.iban_norm = bk.iban_norm
    JOIN konto v              ON v.bp_key = bv.bp_key AND v.role = 'VENDOR'
    WHERE bk.iban_norm IS NOT NULL
),
treffer AS (
    SELECT DISTINCT customer_key, vendor_key, kriterium, feld, wert, referenz
    FROM (SELECT * FROM ust UNION ALL SELECT * FROM bank)
),
cluster AS (
    SELECT
        t.customer_key,
        list_sort(list_distinct(list(t.vendor_key)))                    AS kreditoren,
        list_sort(list_distinct(list(t.kriterium)))                     AS kriterien,
        list_sort(list_distinct(list(t.feld)))                          AS felder,
        list_sort(list_distinct(list(t.wert)))                          AS werte,
        -- Die IBAN steht in `records` nur, wenn sie das Trefferkriterium war: dann ist
        -- sie fuer alle Konten dieselbe. Sonst NULL statt einer willkuerlich gewaehlten.
        max(CASE WHEN t.kriterium = 'Bankverbindung' THEN t.wert END)   AS treffer_iban
    FROM treffer t
    GROUP BY t.customer_key
)
SELECT
    c.customer_key                                AS bp_key,
    'CUSTOMER'                                    AS role,
    NULL                                          AS company_code,
    'KNA1 + LFA1'                                 AS source_table,
    array_to_string(c.felder, ' + ')              AS source_field,
    array_to_string(c.werte, ' / ')               AS current_value,
    'derselbe Geschäftspartner ist als Debitor und als Kreditor geführt (Übereinstimmung: '
        || array_to_string(c.kriterien, ' und ') || ')'
                                                  AS current_display,
    -- Stufe B verlangt ein Soll; hier ist es eine Handlung und kein Wert (D-186, wie
    -- AP-LEA-001). Ein fuehrendes Konto waere das falsche Soll: die beiden Konten
    -- bleiben, sie werden nur miteinander verbunden.
    NULL                                          AS proposed_value,
    'Verrechnung prüfen und beide Konten gegenseitig eintragen – nicht zusammenführen'
                                                  AS proposed_display,
    -- Quellenlage: woran der Treffer haengt. Deterministisch heisst hier woertlich, dass
    -- kein Namens- oder Adressabgleich mitspielt - anders als bei AR-DUP-001 (Sprint 4).
    'Deterministischer Abgleich: ' || array_to_string(c.kriterien, ' und ')
        || ' identisch bei Debitor und '
        || CASE WHEN len(c.kreditoren) = 1 THEN 'einem Kreditorenkonto'
                ELSE len(c.kreditoren)::VARCHAR || ' Kreditorenkonten' END
        || '; kein Namens- oder Adressabgleich'
                                                  AS source_summary,
    (
        SELECT to_json(list({
            'source_type':    'deterministic',
            'reference':      k.referenz,
            'reference_kind': 'master_field',
            'value':          k.wert,
            'observed_at':    NULL,
            'agrees':         TRUE,
            'note':           'dieselbe ' || k.kriterium || ' bei Debitor und Kreditor'
        } ORDER BY k.kriterium))
        FROM (SELECT DISTINCT customer_key, kriterium, wert, referenz FROM treffer) k
        WHERE k.customer_key = c.customer_key
    )                                             AS evidence,
    -- Keine Euro-Wirkung: hier ist kein Geld abgeflossen. Was auf beiden Seiten offen
    -- steht, zeigt `records` je Konto - das Aufrechnungspotenzial selbst ist
    -- CROSS-LEA-001 und nicht diese Regel.
    to_json(c.kreditoren)                         AS related_bp_keys,
    (
        SELECT to_json(list({
            'bp_key': p.bp_key,
            'fields': {
                'name':             p.name1,
                'street':           p.street,
                'postal_code':      p.postal_code,
                'city':             p.city,
                'country':          p.country,
                'vat_id':           (SELECT max(t.value) FROM bp_tax_id t
                                     WHERE t.bp_key = p.bp_key AND t.tax_id_type = 'VAT'),
                'iban_masked':      c.treffer_iban,
                'open_items':       r.open_items_local::VARCHAR,
                'currency':         r.currency,
                'last_activity_on': r.last_activity_on::VARCHAR
            }
        } ORDER BY p.bp_key))
        FROM business_partner p
        LEFT JOIN bp_relevance r
          ON r.bp_key = p.bp_key
        WHERE p.bp_key = c.customer_key
           OR list_contains(c.kreditoren, p.bp_key)
    )                                             AS records,
    to_json({
        'match_label':  array_to_string(c.kriterien, ' und '),
        'match_value':  array_to_string(c.werte, ' / '),
        'kreditoren':   len(c.kreditoren)
    })                                            AS params
FROM cluster c
ORDER BY c.customer_key;
