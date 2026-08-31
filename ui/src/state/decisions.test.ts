/** Entscheidungen der Sitzung: Reducer und die Überlagerung über die Findings. */
import { describe, expect, it } from 'vitest'
import { NO_DECISIONS, applyDecisions, decisionsReducer, effectiveStatus } from '@/state/decisions'
import type { DecisionRecord } from '@/types/decision'
import type { Finding } from '@/types/finding'

function finding(id: string, overrides: Partial<Finding> = {}): Finding {
  return {
    finding_id: id,
    run_id: 'demo',
    rule_id: 'AR-VAL-001',
    rule_version: '1.0',
    engine_version: '0.1.0',
    pack_version: '0.1',
    side: 'AR',
    category: 'validity',
    severity: 'high',
    damage_class: 2,
    tier: 'B',
    action_type: 'review',
    title: 'Beispielbefund für den Test',
    entity: { bp_key: 'C:0000100001', role: 'CUSTOMER' },
    current: { source_table: 'KNA1', source_field: 'STCEG', value: null },
    why: 'Grund für den Test.',
    if_wrong: 'Folge im Test.',
    remediation: { sap_transaction: 'XD02', mass_change_eligible: false },
    status: 'open',
    data_as_of: '2026-08-28',
    created_at: '2026-08-30T09:15:00Z',
    ...overrides,
  }
}

function decision(overrides: Partial<DecisionRecord> = {}): DecisionRecord {
  return {
    finding_id: 'F-000000000001',
    action: 'accept',
    reason_code: null,
    reason: 'Vorschlag übernommen',
    assigned_to: null,
    by: 'V. Test',
    at: '2026-08-30T10:00:00.000Z',
    ...overrides,
  }
}

describe('decisionsReducer', () => {
  it('nimmt eine Entscheidung auf und überschreibt sie bei einer zweiten', () => {
    const erste = decisionsReducer(NO_DECISIONS, { type: 'record', record: decision() })
    expect(erste['F-000000000001'].action).toBe('accept')

    const zweite = decisionsReducer(erste, {
      type: 'record',
      record: decision({ action: 'reject', reason_code: 'data_correct' }),
    })
    expect(Object.keys(zweite)).toHaveLength(1)
    expect(zweite['F-000000000001'].action).toBe('reject')
  })

  it('nimmt eine Entscheidung zurück', () => {
    const mit = decisionsReducer(NO_DECISIONS, { type: 'record', record: decision() })
    const ohne = decisionsReducer(mit, { type: 'clear', findingId: 'F-000000000001' })
    expect(ohne).toEqual({})
  })

  it('lässt den Zustand unberührt, wenn nichts zurückzunehmen ist', () => {
    const mit = decisionsReducer(NO_DECISIONS, { type: 'record', record: decision() })
    expect(decisionsReducer(mit, { type: 'clear', findingId: 'F-999999999999' })).toBe(mit)
    expect(decisionsReducer(NO_DECISIONS, { type: 'reset' })).toBe(NO_DECISIONS)
  })

  it('leert alles beim Laden einer neuen Findings-Datei', () => {
    const mit = decisionsReducer(NO_DECISIONS, { type: 'record', record: decision() })
    expect(decisionsReducer(mit, { type: 'reset' })).toEqual({})
  })
})

describe('applyDecisions', () => {
  const findings = [finding('F-000000000001'), finding('F-000000000002')]

  it('lässt die geladenen Findings unverändert', () => {
    const decisions = { 'F-000000000001': decision() }
    const überlagert = applyDecisions(findings, decisions)
    expect(findings[0].status).toBe('open')
    expect(findings[0].decision).toBeUndefined()
    expect(überlagert[0]).not.toBe(findings[0])
    expect(überlagert[1]).toBe(findings[1])
  })

  it('setzt Status und Entscheidung schemakonform', () => {
    const record = decision({ action: 'assign', assigned_to: 'K. Meier', reason: 'Zugewiesen an K. Meier' })
    const [erstes] = applyDecisions(findings, { 'F-000000000001': record })
    expect(erstes.status).toBe('in_progress')
    // Nur die vier Felder, die `logic/finding.schema.json` unter `decision` kennt.
    expect(Object.keys(erstes.decision ?? {}).sort()).toEqual(['at', 'by', 'reason', 'reason_code'])
    expect(erstes.decision?.by).toBe('V. Test')
  })

  it('gibt ohne Entscheidungen dieselbe Liste zurück', () => {
    expect(applyDecisions(findings, NO_DECISIONS)).toEqual(findings)
  })
})

describe('effectiveStatus', () => {
  it('zeigt den Status des Laufs, bis eine Entscheidung ihn ersetzt', () => {
    const offen = finding('F-000000000001')
    expect(effectiveStatus(offen, NO_DECISIONS)).toBe('open')
    expect(
      effectiveStatus(offen, {
        'F-000000000001': decision({ action: 'reject', reason_code: 'accepted_risk' }),
      }),
    ).toBe('accepted_risk')
  })
})
