/* ---
id: AP-VAL-002
version: "1.0"
title: "USt-IdNr. ohne gültiges Format ({befund})"
side: AP
category: validity
severity: high
damage_class: 2
default_tier: C
default_action_type: review
requires_tables: [business_partner, bp_tax_id]
plain_logic: >
  Finding, wenn die USt-IdNr. (STCEG) eines Kreditors (kein CpD) auf **kein** Formatmuster
  aus `logic/dictionaries/vat_id_patterns.yaml` passt. Das Muster wird über das Präfix des
  **Werts** ausgewählt, nicht über das Sitzland: eine formal richtige österreichische
  Nummer bei einem deutschen Lieferanten ist ein Länder-, kein Formatfehler und gehört zu
  AP-VAL-001 (D-058). Zwei Fälle: der Wert trägt ein Buchstabenpräfix, zu dem es ein Muster
  gibt, und verletzt es – oder er trägt gar kein Buchstabenpräfix und passt auf kein Muster;
  dann sieht er wie eine Steuernummer aus und gehört in STCD1. Ein Buchstabenpräfix **ohne**
  Muster im Wörterbuch ergibt kein Finding – nicht beurteilbar ist nicht falsch; der Lauf
  nennt solche Präfixe als Hinweis. **Kein `proposed`**: das richtige Format sagt nichts
  über die richtige Nummer, dafür braucht es VIES – und ein `proposed`, das nur erklärt,
  warum es kein Soll gibt, sieht aus wie ein leerer Vorschlag (D-186). Was zu tun ist,
  steht unter `remediation`.
why: >
  Eine USt-IdNr. im falschen Format scheitert bei jeder Bestätigungsanfrage. Beim Kreditor
  hängt daran der Vorsteuerabzug: ohne gültige Nummer des Lieferanten ist die Rechnung
  nach § 14 UStG unvollständig, und beim innergemeinschaftlichen Erwerb fehlt die
  Grundlage für die Reverse-Charge-Behandlung. Eine Steuernummer im Feld STCEG ist zugleich
  ein Datenfehler mit Folgen für die Zusammenfassende Meldung. Ein Soll nennt das Finding
  nicht: die richtige Nummer ist erst mit einer Bestätigung über VIES zu ermitteln
  (`--enrich vies`, nicht in diesem Sprint).
if_wrong: >
  Wird eine erfundene Nummer eingetragen, um das Format zu erfüllen, ist der Stammsatz
  formal sauber und fachlich falsch – das ist schlechter als das erkannte Problem. Deshalb
  Review mit Beleg (Rechnung, Vertrag), nicht Massenänderung.
remediation:
  sap_transaction: XK02
  path: "Steuerung → USt-IdNr. / Steuernummer"
  field: STCEG / STCD1
  mass_change_eligible: false
  steps:
    - "Trägt der Wert kein Länderpräfix, sieht er wie eine Steuernummer aus: nach STCD1 umtragen und STCEG leeren (D-058)"
    - "Sonst die richtige USt-IdNr. beim Lieferanten erfragen – aus Vertrag oder Rechnung, nicht aus dem Stammsatz"
    - "Vor der Übernahme über VIES bestätigen lassen; ohne Bestätigung bleibt es Stufe C"
tests:
  # Nur Konten, die `testdata/demo_mandant/defects.yaml` namentlich nennt (D-066).
  hits:
    - "V:0000200061"   # DEF-0042: Steuernummer 446/298/82658 im Feld STCEG
    - "V:0000200067"   # DEF-0043: DE222513 - zu kurz fuer das DE-Muster
    - "V:0000200071"   # DEF-0044: DE9808O7083 - Buchstabe an einer Ziffernstelle
  no_hits:
    - "V:0000200845"   # DEF-0004, Anker F-004: DE811000004 passt zum DE-Muster
    - "V:0000201330"   # DEF-0006, Anker F-006: DE831504744 passt zum DE-Muster
  edge:
    # Fremdes Praefix in gueltigem Format: muss AP-VAL-001 bleiben und hier nicht
    # zusaetzlich auftauchen - sonst traegt jeder Praefixfehler zwei Findings.
    - "V:0000200025"   # DEF-0038
    # Dieselbe Datenlage auf der AR-Seite darf diese Regel nicht liefern (AR-VAL-002).
    - "C:0000100125"   # DEF-0039
--- */
WITH muster(prefix, pattern) AS (
    VALUES ${vat_patterns.rows}
),
werte AS (
    SELECT
        bp.bp_key,
        bp.role,
        bp.country,
        t.value                                   AS vat_value,
        t.value_norm                              AS vat_norm,
        substr(t.value_norm, 1, 2)                AS praefix,
        regexp_matches(substr(t.value_norm, 1, 2), '^[A-Z]{2}$')  AS hat_praefix
    FROM business_partner bp
    JOIN bp_tax_id t
      ON t.bp_key = bp.bp_key AND t.tax_id_type = 'VAT'
    WHERE bp.role = 'VENDOR'
      AND bp.is_one_time = FALSE
),
geprueft AS (
    SELECT
        w.*,
        -- Erst die Musterpruefung: passt der Wert auf irgendein Muster des Woerterbuchs,
        -- ist er formal in Ordnung - unabhaengig davon, ob das Praefix zum Sitzland passt.
        EXISTS (SELECT 1 FROM muster m WHERE regexp_matches(w.vat_norm, m.pattern))
                                                  AS passt_auf_ein_muster,
        (SELECT m.pattern FROM muster m WHERE m.prefix = w.praefix)  AS praefix_muster
    FROM werte w
)
SELECT
    g.bp_key,
    g.role,
    NULL                                          AS company_code,
    'LFA1'                                        AS source_table,
    'STCEG'                                       AS source_field,
    g.vat_value                                   AS current_value,
    CASE
        WHEN g.hat_praefix THEN 'entspricht nicht dem Format für ' || g.praefix
        ELSE 'kein Länderpräfix – sieht wie eine Steuernummer aus'
    END                                           AS current_display,
    -- Kein Soll und deshalb kein proposed (D-186): das Vorgehen steht unter remediation,
    -- die Musterverletzung in der Evidenz.
    NULL                                          AS proposed_value,
    NULL                                          AS proposed_display,
    NULL                                          AS source_summary,
    to_json([{
        'source_type':    'deterministic',
        'reference':      'vat_id_patterns.yaml',
        'reference_kind': 'policy',
        'value':          coalesce(g.praefix_muster, 'kein Muster für dieses Präfix'),
        'observed_at':    NULL,
        'agrees':         FALSE,
        'note':           'Formatmuster nach dem Präfix des Werts, nicht nach dem Sitzland (D-058)'
    }])                                           AS evidence,
    to_json({
        'befund': CASE
            WHEN g.hat_praefix THEN 'Format ' || g.praefix
            ELSE 'ohne Länderpräfix'
        END
    })                                            AS params
FROM geprueft g
WHERE NOT g.passt_auf_ein_muster
  -- Ein Buchstabenpraefix ohne Muster im Woerterbuch ist nicht beurteilbar: kein Finding.
  -- Der Lauf nennt es als Hinweis, damit es beim Onboarding ergaenzt wird (Regel 4).
  AND (NOT g.hat_praefix OR g.praefix_muster IS NOT NULL)
ORDER BY g.bp_key, g.vat_norm;
