/* ---
id: AP-CON-001
version: "1.0"
title: "Dieselbe Bankverbindung bei {konten} Kreditoren ({iban_masked})"
side: AP
category: consistency
severity: critical
damage_class: 1
default_tier: C
default_action_type: review
requires_tables: [business_partner, bp_bank_account, bp_company_code, bp_partner_function, bp_relevance]
plain_logic: >
  Finding, wenn dieselbe IBAN bei mehr als einem Kreditorenkonto (kein CpD) hinterlegt ist
  und die beteiligten Konten **nicht** über einen Regulierer zusammenhängen. Als
  Regulierer-Bezug gilt: eines der Konten nennt ein anderes des Clusters als abweichenden
  Zahlungsempfänger – zentral (LFA1-LNRZA) oder buchungskreisabhängig (LFB1-LNRZB) – oder
  eine Partnerrolle verbindet die beiden. Ein Zentralregulierer *soll* die Bankverbindung
  seiner Mitglieder tragen; das ist die gewollte Gestaltung und kein Befund.
  **Ein Finding je IBAN, nicht je Konto:** die Bearbeiterin entscheidet einmal über das
  Cluster, nicht zweimal über dieselbe Sache. Anker ist der kleinste `bp_key`; die
  übrigen Konten stehen in `related_bp_keys`, und `entity.records` trägt je Konto die
  Vergleichsfelder (D-069 Punkt 3 und 4). Kein Soll: welches Konto das richtige ist – oder
  ob beide bleiben – ist eine Entscheidung mit Blick in die Beziehung, nicht aus den Daten
  ableitbar (D-186). Schadensklasse 1: die IBAN steht ausschließlich maskiert im Finding,
  auffindbar über Bankschlüssel und Bankdetail-ID (D-105). `payment_terms` bleibt in
  `records` weg – die Zahlungsbedingung hängt am Buchungskreis, und ein Konto kann mehrere
  haben; einseitig gefüllt zeigte die Vergleichstabelle eine Abweichung, wo nur eine
  Angabe uneindeutig ist.
why: >
  Zwei Kreditorenkonten mit derselben Bankverbindung sind entweder eine Dublette – dann
  wird dieselbe Leistung zweimal bezahlt, ohne dass die Doppelerfassungsprüfung anschlägt,
  weil die Kontonummern verschieden sind – oder eine umgeleitete Zahlung: ein angelegtes
  Konto, dessen Bankdaten auf ein bestehendes zeigen, ist das klassische Muster des
  Zahlungsbetrugs. Beide Fälle sehen in der Buchhaltung unauffällig aus und fallen nur
  über die Bankverbindung auf.
if_wrong: >
  Wird die Verbindung vorschnell aufgelöst und die Bankverbindung beim falschen Konto
  gelöscht, bleibt eine berechtigte Zahlung liegen; wird das falsche Konto gesperrt,
  stockt die Lieferbeziehung. Ist es dagegen wirklich eine umgeleitete Zahlung, ist jede
  Zahlung bis zur Klärung verloren. Deshalb Stufe C: prüfen und entscheiden, nichts
  automatisch ändern – und die Prüfung über einen bekannten Kanal, nie über die
  Kontaktdaten des jüngeren Kontos.
remediation:
  sap_transaction: XK02
  path: "Zahlungsverkehr → Bankverbindungen"
  field: IBAN
  mass_change_eligible: false
  steps:
    - "Beide Stammsätze vergleichen (Name, Adresse, USt-IdNr., Anlagedatum) – die Vergleichsfelder stehen im Finding"
    - "Prüfen, ob ein Regulierer gewollt, aber nicht gepflegt ist: dann LNRZA/LNRZB nachtragen statt die Bankverbindung zu ändern"
    - "Ist es eine Dublette: führendes Konto bestimmen, das andere zur Löschung vormerken (XK06), offene Posten vorher umbuchen"
    - "Ist keines von beidem erklärbar: Zahlsperre setzen und die Bankverbindung über einen bekannten Kanal beim Lieferanten bestätigen lassen"
tests:
  # Nur Konten, die `testdata/demo_mandant/defects.yaml` namentlich nennt (D-066).
  hits:
    - "V:0000200193"   # DEF-0110: Anker des Clusters (V:0000200194 ist das zweite Konto)
    - "V:0000200195"   # DEF-0111
    - "V:0000200204"   # DEF-0113
  no_hits:
    # Die zweiten Konten der Cluster: sie stehen im Finding des Ankers, tragen aber
    # keines eigenen - ein Finding je IBAN, nicht je Konto.
    - "V:0000200194"   # DEF-0110
    - "V:0000200203"   # DEF-0112
    - "V:0000200845"   # DEF-0004, Anker F-004: Bankverbindung nur einmal vergeben
  edge:
    # Der Regulierer-Ausschluss ist im Demo-Mandanten **nicht ausgeuebt**: alle
    # `central_payer`-Defekte (DEF-0120 ff.) sind Debitoren, und kein Kreditor traegt
    # einen alt_payer_key. Die Klausel steht trotzdem - sie ist die Voraussetzung dafuer,
    # dass die Regel auf einem echten Mandanten mit Zentralregulierung nicht jeden
    # Regulierer meldet. Sobald ein AP-`central_payer`-Defekt in defects.yaml steht,
    # gehoert sein Mitgliedskonto hierher (Victors Posten, R2).
    # Bis dahin die AR-Seite als Gegenprobe: dieselbe Datenlage dort gehoert zu
    # AR-CON-004 (noch nicht gebaut), nie hierher.
    - "C:0000100306"   # DEF-0120: Zentralregulierer auf der Debitorenseite
--- */
WITH konto AS (
    SELECT
        b.iban_norm,
        b.bp_key,
        b.bank_key,
        b.partner_bank_type
    FROM bp_bank_account b
    JOIN business_partner bp
      ON bp.bp_key = b.bp_key
    WHERE bp.role = 'VENDOR'
      AND bp.is_one_time = FALSE
      AND b.iban_norm IS NOT NULL
),
cluster AS (
    SELECT
        k.iban_norm,
        count(DISTINCT k.bp_key)                        AS konten,
        min(k.bp_key)                                   AS anker,
        list(DISTINCT k.bp_key ORDER BY k.bp_key)       AS mitglieder,
        min(k.bank_key)                                 AS bank_key,
        min(k.partner_bank_type)                        AS partner_bank_type
    FROM konto k
    GROUP BY k.iban_norm
    HAVING count(DISTINCT k.bp_key) > 1
)
SELECT
    c.anker                                       AS bp_key,
    'VENDOR'                                      AS role,
    NULL                                          AS company_code,
    'TIBAN'                                       AS source_table,
    'IBAN'                                        AS source_field,
    -- Schadensklasse 1: nur die ersten und letzten vier Stellen, nie die ganze IBAN
    -- (CLAUDE.md Regel 8, Maske nach logic/finding.schema.json $defs.iban_masked)
    substr(c.iban_norm, 1, 4) || ' … ' || substr(c.iban_norm, -4)  AS current_value,
    'bei ' || c.konten::VARCHAR || ' Kreditorenkonten hinterlegt, ohne Regulierer-Bezug'
                                                  AS current_display,
    -- Kein Soll und deshalb kein proposed (D-186): welches Konto bleibt, ist eine
    -- Entscheidung mit Blick in die Lieferantenbeziehung. Das Vorgehen steht unter
    -- remediation, die Vergleichsfelder in entity.records.
    NULL                                          AS proposed_value,
    NULL                                          AS proposed_display,
    NULL                                          AS source_summary,
    to_json([
        {
            'source_type':    'deterministic',
            -- Bankschluessel und Bankdetail-ID identifizieren die Bankverbindung im
            -- Stammsatz, ohne die Kontonummer zu nennen (D-105)
            'reference':      'TIBAN BANKL ' || coalesce(c.bank_key, '–')
                              || ' / BVTYP ' || coalesce(c.partner_bank_type, '–'),
            'reference_kind': 'master_field',
            'value':          substr(c.iban_norm, 1, 4) || ' … ' || substr(c.iban_norm, -4),
            'observed_at':    NULL,
            'agrees':         FALSE,
            'note':           'dieselbe IBAN bei ' || c.konten::VARCHAR || ' Konten'
        },
        {
            'source_type':    'deterministic',
            'reference':      'LFA1-LNRZA / LFB1-LNRZB / Partnerrollen',
            'reference_kind': 'master_field',
            'value':          'kein Regulierer hinterlegt',
            'observed_at':    NULL,
            'agrees':         FALSE,
            'note':           'Ein Zentralregulierer traegt die Bankverbindung seiner Mitglieder zu Recht; hier verbindet die Konten keiner'
        }
    ])                                            AS evidence,
    to_json(c.mitglieder[2:])                     AS related_bp_keys,
    -- Je beteiligtem Konto die Vergleichsfelder (D-069 Punkt 3); der Anker steht mit
    -- darin, sonst fehlte in der Tabelle genau die Zeile, gegen die verglichen wird.
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
                'iban_masked':      substr(c.iban_norm, 1, 4) || ' … ' || substr(c.iban_norm, -4),
                'open_items':       r.open_items_local::VARCHAR,
                'currency':         r.currency,
                'last_activity_on': r.last_activity_on::VARCHAR
            }
        } ORDER BY p.bp_key))
        FROM business_partner p
        LEFT JOIN bp_relevance r
          ON r.bp_key = p.bp_key
        WHERE list_contains(c.mitglieder, p.bp_key)
    )                                             AS records,
    to_json({
        'konten':             c.konten,
        'iban_masked':        substr(c.iban_norm, 1, 4) || ' … ' || substr(c.iban_norm, -4),
        'bank_key':           c.bank_key,
        'partner_bank_type':  c.partner_bank_type
    })                                            AS params
FROM cluster c
-- Regulierer-Ausschluss: verbindet einer der drei SAP-Wege zwei Konten des Clusters,
-- ist die gemeinsame Bankverbindung gewollt und kein Befund.
WHERE NOT EXISTS (
    SELECT 1 FROM business_partner z
    WHERE list_contains(c.mitglieder, z.bp_key)
      AND list_contains(c.mitglieder, z.alt_payer_key)
      AND z.alt_payer_key <> z.bp_key
)
  AND NOT EXISTS (
    SELECT 1 FROM bp_company_code z
    WHERE list_contains(c.mitglieder, z.bp_key)
      AND list_contains(c.mitglieder, z.alt_payer_key)
      AND z.alt_payer_key <> z.bp_key
)
  AND NOT EXISTS (
    SELECT 1 FROM bp_partner_function f
    WHERE list_contains(c.mitglieder, f.bp_key)
      AND list_contains(c.mitglieder, f.partner_bp_key)
      AND f.partner_bp_key <> f.bp_key
)
ORDER BY c.anker;
