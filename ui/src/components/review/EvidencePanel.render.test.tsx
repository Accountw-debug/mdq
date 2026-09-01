/**
 * Evidenz-Panel: der Satz über den Karten, der die Widersprüche ankündigt.
 *
 * Aufgefallen in der Handprobe am Lauf 2026-08-28-702323b8: bei zwei
 * widersprechenden Einträgen stand „2 Einträge widersprechen dem Soll und
 * **steht** zuerst" – nur der erste Teil des Satzes wurde in den Plural gesetzt.
 * Beide Formen stehen deshalb hier als Test.
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { EvidencePanel } from '@/components/review/EvidencePanel'
import type { Evidence, Finding } from '@/types/finding'

/** Ein Eintrag, der dem Soll widerspricht – die Referenz unterscheidet die Karten. */
function contradicting(reference: string): Evidence {
  return {
    source_type: 'deterministic',
    reference,
    value: 'nicht gesetzt',
    observed_at: null,
    agrees: false,
    note: null,
  }
}

/** Gerüst nach dem Muster von AP-CON-001; gelesen wird nur `evidence`. */
function finding(evidence: Evidence[]): Finding {
  return {
    finding_id: 'F-000000000009',
    run_id: 'demo',
    rule_id: 'AP-CON-001',
    rule_version: '1.0',
    engine_version: '0.1.0',
    pack_version: '0.1',
    side: 'AP',
    category: 'consistency',
    severity: 'critical',
    damage_class: 1,
    tier: 'C',
    action_type: 'review',
    title: 'Dieselbe Bankverbindung bei 2 Kreditoren',
    entity: { bp_key: 'V:0000200193', role: 'VENDOR' },
    current: { source_table: 'TIBAN', source_field: 'IBAN', value: null, display: null },
    evidence,
    why: 'Prüftext',
    if_wrong: 'Prüftext',
    remediation: { sap_transaction: 'XK02', mass_change_eligible: false, steps: [] },
    status: 'open',
    data_as_of: '2026-08-28',
    created_at: '2026-08-31T22:17:53Z',
  }
}

const render = (evidence: Evidence[]) =>
  renderToStaticMarkup(<EvidencePanel finding={finding(evidence)} />)

describe('EvidencePanel', () => {
  it('setzt den Satz bei einem Widerspruch in den Singular', () => {
    const html = render([contradicting('TIBAN BANKL 97826974')])
    expect(html).toContain('Ein Eintrag widerspricht dem Soll und steht zuerst.')
    expect(html).not.toContain('stehen zuerst')
  })

  it('setzt den ganzen Satz bei mehreren Widersprüchen in den Plural', () => {
    const html = render([
      contradicting('TIBAN BANKL 97826974'),
      contradicting('LFA1-LNRZA / LFB1-LNRZB'),
    ])
    expect(html).toContain('2 Einträge widersprechen dem Soll und stehen zuerst.')
    expect(html).not.toContain('steht zuerst')
  })
})
