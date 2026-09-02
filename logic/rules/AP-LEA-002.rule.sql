/* ---
id: AP-LEA-002
version: "1.0"
title: "Skontoverlust 12 Monate: {loss} bei {invoices} Rechnungen"
side: AP
category: leakage
severity: medium
damage_class: 3
default_tier: C
default_action_type: process
requires_tables: [business_partner, company_code, fi_item, payment_terms]
parameters:
  # Meldegrenze des realisierten Verlusts je Kreditor und Buchungskreis, in der
  # Hauswaehrung des Buchungskreises. Unterhalb lohnt der Prozessanstoss nicht.
  # Als Zeichenkette und nicht als Zahl: eine Schwelle, die ein Betrag ist, darf nicht
  # durch ein float (Regel 2); das SQL castet sie nach DECIMAL.
  min_loss: "1000.00"
  # Laenge des Betrachtungsfensters in Monaten, zurueck vom Datenstand des Laufs.
  months: 12
plain_logic: >
  Finding je Kreditor und Buchungskreis, wenn in den letzten `${params.months}` Monaten
  vor dem Datenstand Skonto verfallen ist. Das Fenster ist **links offen und rechts
  geschlossen** wie das Relevanzfenster (D-087): `Buchungsdatum > Datenstand −
  ${params.months} Monate` und `<= Datenstand`. Der Beleg vom Tag der unteren Grenze
  gehörte sonst in zwei aufeinanderfolgende Fenster, und eine Buchung nach dem Datenstand
  kann ein Export nicht enthalten – nennt der Lauf einen früheren Datenstand, gehört sie
  nicht dazu. Gezählt wird eine Rechnung als Verlust, wenn sie eine
  Skontovereinbarung trägt (ZBD1P > 0 mit ZBD1T und Basisdatum ZFBDT), **ausgeglichen**
  ist, **kein** Skonto gezogen wurde (SKNTO = 0) und der Ausgleich nach dem Ende der
  Skontofrist lag. Der Verlust je Rechnung ist Skontobasis × Prozentsatz; der Lauf
  meldet, sobald die Summe `${params.min_loss}` erreicht.
  **Drei Töpfe, und nur einer ist der Schaden:** *realisiert* sind die bezahlten, zu spät
  ausgeglichenen Rechnungen – dieses Geld ist weg, es allein trägt `impact_eur` und
  entscheidet über die Meldegrenze. *Verfallen-unbezahlt* sind offene Rechnungen, deren
  Skontofrist am Datenstand schon vorbei ist – auch dort ist nichts mehr zu holen.
  *Vermeidbar* sind offene Rechnungen, deren Frist noch läuft: nur dieser Betrag ist
  ein Versprechen, das der Bericht halten kann. Die beiden offenen Töpfe stehen in der
  Evidenz und, wenn etwas zu retten ist, im Handlungssatz.
  Der Stichtag kommt aus dem Lauf (`${scope.data_as_of}`), nie aus `current_date` –
  derselbe Input muss dieselben Findings liefern (Regel 9). Gerechnet wird nur über
  Posten in der Hauswährung des Buchungskreises; Rechnungen in Fremdwährung nennt die
  Evidenz, statt sie stillschweigend wegzulassen (Regel 4).
why: >
  Skonto ist der billigste Kredit, den es gibt: 2 % bei 16 Tagen früherer Zahlung
  entspricht über 40 % p. a. Verpasstes Skonto ist realer, wiederkehrender Abfluss – und
  fast immer kein Einzelfall, sondern ein Takt: der Zahllauf trifft die Frist
  systematisch nicht.
if_wrong: >
  Kein Datenfehler – es wird nichts am Stammsatz geändert, nur ein Prozessvorschlag
  gemacht. Die Liquidität muss den früheren Zahllauf hergeben; wo sie das nicht tut, ist
  der verspätete Ausgleich eine bewusste Finanzierungsentscheidung und kein Befund. Der
  bereits realisierte Verlust ist in keinem Fall rückholbar; wer ihn im Bericht als
  Einsparung liest, plant mit Geld, das schon aus dem Haus ist.
remediation:
  sap_transaction: F110
  path: "Zahllauf-Parameter: Termin/Frequenz oder Zahlwegauswahl für diesen Kreditor"
  field: null
  mass_change_eligible: false
  steps:
    - "Zahllauf-Frequenz oder 'nächstes Buchungsdatum' so setzen, dass die Skontofrist erreicht wird"
    - "Offene Rechnungen mit laufender Skontofrist vorziehen – nur dort ist noch etwas zu holen"
    - "Alternativ Zahlungsbedingung mit dem Lieferanten neu verhandeln"
tests:
  # Nur Konten, die `testdata/demo_mandant/defects.yaml` namentlich nennt (D-066).
  hits:
    - "V:0000200117"   # DEF-0005, Anker F-005: 23 von 31 Rechnungen zu spaet
    - "V:0000200177"   # DEF-0083: durchgehend nach der Skontofrist bezahlt
    - "V:0000200190"   # DEF-0088
  no_hits:
    # Negativfaelle des Generators: Skonto innerhalb der Frist gezogen (late: false)
    - "C:0000100280"   # DEF-0106
    - "C:0000100282"   # DEF-0107
    - "V:0000200845"   # DEF-0004, Anker F-004: kein Skontoverlust
  edge:
    # Dieselbe Datenlage auf der AR-Seite (Skonto zu spaet gezogen) gehoert zu AR-LEA-003
    # und nicht hierher; der Rollenfilter haelt das.
    - "C:0000100284"   # DEF-0109
--- */
WITH posten AS (
    SELECT
        i.bp_key,
        i.company_code,
        i.currency,
        i.payment_terms,
        i.is_open,
        i.cash_disc_pct1,
        i.cash_disc_base,
        i.baseline_date,
        i.clearing_date,
        i.cash_disc_taken,
        -- Ende der Skontofrist: Basisdatum plus vereinbarte Tage
        i.baseline_date + i.cash_disc_days1                       AS skontofrist,
        i.cash_disc_days1                                         AS skontotage,
        -- Eine Rechnung mit Skontovereinbarung: ohne Satz, Tage oder Basisdatum ist
        -- "Frist versaeumt" nicht entscheidbar - dann ist sie kein Fall dieser Regel.
        (i.cash_disc_pct1 > 0
         AND i.cash_disc_days1 IS NOT NULL
         AND i.baseline_date IS NOT NULL
         AND i.cash_disc_base IS NOT NULL)                        AS mit_skonto
    FROM fi_item i
    JOIN company_code cc
      ON cc.company_code = i.company_code
    WHERE i.doc_type IN (${doc_types.AP.invoice})
      -- Links offen, rechts geschlossen wie das Relevanzfenster (D-087, D-206):
      -- der Beleg vom Tag der unteren Grenze gehoerte sonst in zwei Fenster.
      AND i.posting_date >  ${scope.data_as_of} - INTERVAL ${params.months} MONTH
      AND i.posting_date <= ${scope.data_as_of}
      -- Skontobasis und -betrag stehen in Belegwaehrung; nur Hauswaehrungsposten sind
      -- ohne Umrechnung summierbar (Regel 2, D-030). Fremdwaehrung wird nicht
      -- weggelassen, sondern unten gezaehlt und genannt (Regel 4).
      AND i.currency = cc.currency
),
fremd AS (
    SELECT i.bp_key, i.company_code, count(*) AS rechnungen
    FROM fi_item i
    JOIN company_code cc
      ON cc.company_code = i.company_code
    WHERE i.doc_type IN (${doc_types.AP.invoice})
      -- Links offen, rechts geschlossen wie das Relevanzfenster (D-087, D-206):
      -- der Beleg vom Tag der unteren Grenze gehoerte sonst in zwei Fenster.
      AND i.posting_date >  ${scope.data_as_of} - INTERVAL ${params.months} MONTH
      AND i.posting_date <= ${scope.data_as_of}
      AND i.currency <> cc.currency
      AND i.cash_disc_pct1 > 0
    GROUP BY i.bp_key, i.company_code
),
je_konto AS (
    SELECT
        p.bp_key,
        p.company_code,
        min(p.currency)                                           AS currency,
        count(*)                                                  AS rechnungen,
        -- Topf 1: bezahlt und zu spaet - dieses Geld ist weg
        count(*) FILTER (WHERE p.verloren)                        AS spaet,
        (sum(p.cash_disc_base * p.cash_disc_pct1)
            FILTER (WHERE p.verloren) * 0.01)::DECIMAL(15,2)      AS verlust,
        (sum(p.cash_disc_base)
            FILTER (WHERE p.verloren))::DECIMAL(15,2)             AS skontobasis,
        -- Topf 2: offen, Frist am Stichtag vorbei - auch dort ist nichts mehr zu holen
        count(*) FILTER (WHERE p.verfallen_offen)                 AS offen_verfallen,
        coalesce((sum(p.cash_disc_base * p.cash_disc_pct1)
            FILTER (WHERE p.verfallen_offen) * 0.01)::DECIMAL(15,2), 0.00)  AS betrag_verfallen,
        -- Topf 3: offen, Frist laeuft noch - nur das ist vermeidbar
        count(*) FILTER (WHERE p.vermeidbar)                      AS offen_laufend,
        coalesce((sum(p.cash_disc_base * p.cash_disc_pct1)
            FILTER (WHERE p.vermeidbar) * 0.01)::DECIMAL(15,2), 0.00)       AS betrag_vermeidbar,
        -- Die Zahlungsbedingung der zu spaet bezahlten Rechnungen
        max(p.payment_terms) FILTER (WHERE p.verloren)            AS zterm,
        max(p.cash_disc_pct1) FILTER (WHERE p.verloren)           AS pct,
        max(p.skontotage) FILTER (WHERE p.verloren)               AS skontotage,
        round(avg(date_diff('day', p.baseline_date, p.clearing_date))
            FILTER (WHERE p.verloren))::BIGINT                    AS tag_mittel,
        min(date_diff('day', p.baseline_date, p.clearing_date))
            FILTER (WHERE p.verloren)                             AS tag_von,
        max(date_diff('day', p.baseline_date, p.clearing_date))
            FILTER (WHERE p.verloren)                             AS tag_bis
    FROM (
        SELECT
            p.*,
            (p.mit_skonto AND NOT p.is_open
             -- Gezogenes Skonto ist kein Verlust; NULL heisst hier "keines gezogen"
             AND coalesce(p.cash_disc_taken, 0) = 0
             AND p.clearing_date > p.skontofrist)                                 AS verloren,
            (p.mit_skonto AND p.is_open AND p.skontofrist <  ${scope.data_as_of}) AS verfallen_offen,
            (p.mit_skonto AND p.is_open AND p.skontofrist >= ${scope.data_as_of}) AS vermeidbar
        FROM posten p
    ) p
    GROUP BY p.bp_key, p.company_code
)
SELECT
    k.bp_key,
    bp.role,
    k.company_code,
    'BSAK'                                        AS source_table,
    'SKNTO'                                       AS source_field,
    '0.00'                                        AS current_value,
    k.spaet::VARCHAR || ' von ' || k.rechnungen::VARCHAR
        || ' Rechnungen nach Skontofrist bezahlt (Zahlungsbedingung ' || k.zterm
        || ': ' || coalesce(mdq_payment_terms_text(k.zterm), k.skontotage::VARCHAR || ' Tage')  || ')'
                                                  AS current_display,
    -- Kein Soll als Wert: hier ist kein Feld falsch, sondern ein Takt. Der Handlungssatz
    -- ist das Soll (D-186) - und er verspricht nur, was noch zu holen ist.
    NULL                                          AS proposed_value,
    'Zahllauf-Timing für diesen Kreditor prüfen'
        || CASE WHEN k.offen_laufend > 0
                THEN '; noch vermeidbar: ' || mdq_money(k.betrag_vermeidbar, k.currency)
                     || ' auf ' || k.offen_laufend::VARCHAR
                     || CASE WHEN k.offen_laufend = 1 THEN ' offenen Rechnung'
                             ELSE ' offenen Rechnungen' END
                     || ' mit laufender Skontofrist'
                ELSE '; der Verlust ist realisiert, an diesen Rechnungen ist nichts mehr zu holen'
           END                                    AS proposed_display,
    'Zahlungen im Mittel am Tag ' || k.tag_mittel::VARCHAR
        || ' nach Skonto-Basisdatum, Skontofrist Tag ' || k.skontotage::VARCHAR
                                                  AS source_summary,
    -- json_array statt to_json([...]): DuckDB vereinheitlicht die Felder einer
    -- Struct-Liste und schriebe dem Customizing-Eintrag ein leeres reference_kind
    -- hinein. Es traegt zu Recht keines - T052 ist keiner der acht Werte (D-069).
    json_array(
        to_json({
            'source_type':    'statistics',
            -- Der Zeitraum steht taggenau: "2025-08..2026-08" liest sich wie volle
            -- Monate, das Fenster beginnt aber am Stichtag minus zwoelf Monate.
            -- Genannt wird der **erste eingeschlossene** Tag, nicht die ausgeschlossene
            -- untere Grenze: das Fenster ist links offen (D-087), und ein Zeiger, der
            -- sich inklusiv liest, aber exklusiv gemeint ist, ist unwahr (D-206).
            'reference':      'BSAK '
                              || (${scope.data_as_of} - INTERVAL ${params.months} MONTH
                                  + INTERVAL 1 DAY)::DATE::VARCHAR
                              || '..' || ${scope.data_as_of}::VARCHAR,
            'reference_kind': 'statement',
            'value':          k.spaet::VARCHAR || ' Rechnungen, Skontobasis '
                              || mdq_money(k.skontobasis, k.currency) || ', Skonto '
                              || trim(trailing '.' from trim(trailing '0' from k.pct::VARCHAR))
                              || ' % nicht genutzt',
            'observed_at':    ${scope.data_as_of}::VARCHAR,
            'agrees':         TRUE,
            'note':           'Zahlungen Tag ' || k.tag_von::VARCHAR || '–' || k.tag_bis::VARCHAR
                              || ' nach Skonto-Basisdatum'
                              || CASE WHEN f.rechnungen IS NULL THEN ''
                                      ELSE '; ' || f.rechnungen::VARCHAR
                                           || ' Rechnungen in Fremdwährung nicht mitgerechnet'
                                 END
        }),
        to_json({
            'source_type':    'deterministic',
            'reference':      'T052 ' || k.zterm,
            'value':          coalesce(mdq_payment_terms_text(k.zterm), k.skontotage::VARCHAR || ' Tage'),
            'observed_at':    NULL,
            'agrees':         TRUE,
            'note':           'Zahlungsbedingung laut LFB1'
        }),
        to_json({
            'source_type':    'statistics',
            'reference':      'BSIK (offene Posten)',
            'reference_kind': 'statement',
            'value':          k.offen_verfallen::VARCHAR || ' offene Rechnungen mit abgelaufener Skontofrist ('
                              || mdq_money(k.betrag_verfallen, k.currency) || ' verfallen), '
                              || k.offen_laufend::VARCHAR || ' mit laufender Frist ('
                              || mdq_money(k.betrag_vermeidbar, k.currency) || ' vermeidbar)',
            'observed_at':    ${scope.data_as_of}::VARCHAR,
            'agrees':         FALSE,
            'note':           'Nur der Betrag mit laufender Frist ist noch zu holen; der Rest ist verfallen'
        })
    )                                             AS evidence,
    k.verlust                                     AS impact_amount,
    k.currency                                    AS impact_currency,
    'Skontobasis ' || mdq_money(k.skontobasis, k.currency) || ' × '
        || trim(trailing '.' from trim(trailing '0' from k.pct::VARCHAR))
        || ' % = ' || mdq_money(k.verlust, k.currency)
        || ' (nur Rechnungen, die nach Skontofrist bezahlt wurden)'
                                                  AS impact_formula,
    to_json({
        'loss':     mdq_money(k.verlust, k.currency),
        'invoices': k.spaet
    })                                            AS params
FROM je_konto k
JOIN business_partner bp
  ON bp.bp_key = k.bp_key
LEFT JOIN fremd f
  ON f.bp_key = k.bp_key AND f.company_code = k.company_code
WHERE bp.role = 'VENDOR'
  AND bp.is_one_time = FALSE
  -- Die Meldegrenze gilt auf dem realisierten Verlust: was noch zu holen ist, ist kein
  -- Schaden, und was verfallen und unbezahlt ist, wird nicht doppelt gezaehlt.
  AND k.verlust >= ${params.min_loss}::DECIMAL(15,2)
ORDER BY k.bp_key, k.company_code;
