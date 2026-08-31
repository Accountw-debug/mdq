/**
 * Regelgruppen und Stichproben-Freigabe (Aufgabe 7).
 *
 * Drei Zusagen stehen hier auf dem Prüfstand: die Auswahl ist reproduzierbar
 * (Regel 9), Schadensklasse 1 kommt nie in eine Gruppenfreigabe (Regel 11), und
 * eine Freigabe setzt `in_progress` – nicht `done`.
 */
import { describe, expect, it } from 'vitest'
import { statusForDecision } from '@/lib/review'
import {
  SAMPLE_SIZE,
  buildGroupBlock,
  buildGroupRelease,
  drawSample,
  groupByRule,
  nextSampleStep,
  releaseReason,
  sampleCandidates,
  sampleForGroup,
  sampleProgress,
  sampleSeed,
} from '@/lib/sampling'
import type { DecisionsState } from '@/state/decisions'
import type { DecisionRecord } from '@/types/decision'
import type { Finding } from '@/types/finding'

const CLOCK = () => '2026-08-30T10:00:00.000Z'

function finding(id: string, overrides: Partial<Finding> = {}): Finding {
  return {
    finding_id: id,
    run_id: 'demo-2026-08-30',
    rule_id: 'AR-CMP-001',
    rule_version: '1.0',
    engine_version: '0.1.0',
    pack_version: '0.1',
    side: 'AR',
    category: 'completeness',
    severity: 'medium',
    damage_class: 3,
    tier: 'A',
    action_type: 'mass_change',
    title: 'USt-IdNr. fehlt',
    entity: { bp_key: `C:${id}`, role: 'CUSTOMER' },
    current: { source_table: 'KNA1', source_field: 'STCEG', value: null },
    why: 'Grund für den Test.',
    if_wrong: 'Folge im Test.',
    remediation: { sap_transaction: 'XD02', mass_change_eligible: true },
    status: 'open',
    data_as_of: '2026-08-28',
    created_at: '2026-08-30T09:15:00Z',
    ...overrides,
  }
}

/** `n` Findings derselben Regel, durchnummeriert. */
function many(count: number, overrides: Partial<Finding> = {}): Finding[] {
  return Array.from({ length: count }, (_, index) =>
    finding(`F-${String(index + 1).padStart(4, '0')}`, overrides),
  )
}

function decisions(...records: DecisionRecord[]): DecisionsState {
  return Object.fromEntries(records.map((entry) => [entry.finding_id, entry]))
}

function record(findingId: string, overrides: Partial<DecisionRecord> = {}): DecisionRecord {
  return {
    finding_id: findingId,
    action: 'accept',
    reason_code: null,
    reason: 'Vorschlag übernommen',
    assigned_to: null,
    by: 'V. Test',
    at: '2026-08-30T09:50:00.000Z',
    ...overrides,
  }
}

describe('groupByRule', () => {
  it('fasst je Regel zusammen und zählt offen, freigebbar und Bankdaten', () => {
    const groups = groupByRule([
      ...many(3),
      finding('F-9001', { status: 'rejected' }),
      finding('F-9002', { damage_class: 1 }),
      finding('F-8001', { rule_id: 'AP-VAL-002', title: 'Andere Regel' }),
    ])

    expect(groups.map((group) => group.rule_id)).toEqual(['AP-VAL-002', 'AR-CMP-001'])
    const [, erste] = groups
    expect(erste.total).toBe(5)
    expect(erste.open).toBe(4)
    expect(erste.releasable).toBe(3)
    expect(erste.bankData).toBe(1)
  })

  it('sortiert nach Euro-Wirkung absteigend, bei Gleichstand nach Regel-ID', () => {
    const groups = groupByRule([
      finding('F-1', { rule_id: 'AR-CMP-001' }),
      finding('F-2', {
        rule_id: 'AP-LEA-009',
        impact_eur: { amount: '1000.00', currency: 'EUR', formula: '1 × 1.000,00 €' },
      }),
      finding('F-3', { rule_id: 'ZZ-XXX-001' }),
    ])
    expect(groups.map((group) => group.rule_id)).toEqual([
      'AP-LEA-009',
      'AR-CMP-001',
      'ZZ-XXX-001',
    ])
  })

  it('meldet gemischte Stufen, statt eine davon zu verschweigen', () => {
    const [group] = groupByRule([finding('F-1'), finding('F-2', { tier: 'B' })])
    expect(group.mixedTier).toBe(true)
  })
})

describe('drawSample', () => {
  const ids = many(30).map((entry) => entry.finding_id)
  const seed = sampleSeed('demo-2026-08-30', 'AR-CMP-001')

  it('zieht bei gleichem Seed immer dieselbe Stichprobe (Regel 9)', () => {
    expect(drawSample(ids, seed)).toEqual(drawSample(ids, seed))
  })

  it('zieht in einem anderen Lauf eine andere Stichprobe', () => {
    const anderer = sampleSeed('demo-2026-09-30', 'AR-CMP-001')
    expect(drawSample(ids, anderer)).not.toEqual(drawSample(ids, seed))
  })

  it('hängt nicht an der Reihenfolge der übergebenen Liste', () => {
    const gedreht = [...ids].reverse()
    expect(new Set(drawSample(gedreht, seed))).toEqual(new Set(drawSample(ids, seed)))
  })

  it('gibt die Auswahl in der Reihenfolge der Liste zurück', () => {
    const gezogen = drawSample(ids, seed)
    expect(gezogen).toEqual(ids.filter((id) => gezogen.includes(id)))
  })

  it('zieht höchstens zehn und bei weniger Kandidaten alle', () => {
    expect(drawSample(ids, seed)).toHaveLength(SAMPLE_SIZE)
    const drei = ids.slice(0, 3)
    expect(drawSample(drei, seed)).toEqual(drei)
    expect(drawSample([], seed)).toEqual([])
  })
})

describe('sampleCandidates', () => {
  it('lässt Schadensklasse 1 und bereits entschiedene Findings aus (Regel 11)', () => {
    const [group] = groupByRule([
      finding('F-1'),
      finding('F-2', { damage_class: 1 }),
      finding('F-3', { status: 'in_progress' }),
    ])
    expect(sampleCandidates(group).map((entry) => entry.finding_id)).toEqual(['F-1'])
    expect(sampleForGroup(group)).toEqual(['F-1'])
  })
})

describe('sampleProgress', () => {
  it('zählt übernommen und zugewiesen und nennt die erste Ablehnung', () => {
    const stand = sampleProgress(
      ['F-1', 'F-2', 'F-3', 'F-4'],
      decisions(
        record('F-1'),
        record('F-2', { action: 'assign', assigned_to: 'Team Stammdaten' }),
        record('F-3', { action: 'reject', reason_code: 'data_correct' }),
      ),
    )
    expect(stand).toEqual({
      size: 4,
      decided: 3,
      accepted: 1,
      assigned: 1,
      rejectedId: 'F-3',
    })
  })
})

describe('buildGroupRelease', () => {
  const findings = [
    ...many(4),
    finding('F-9001', { damage_class: 1 }),
    finding('F-9002', { status: 'rejected' }),
  ]
  const [group] = groupByRule(findings)
  const stichprobe = ['F-0001', 'F-0002']
  const stand = decisions(record('F-0001'), record('F-0002'))

  it('entscheidet die noch offenen Findings der Gruppe – ohne Bankdaten (Regel 11)', () => {
    const { records } = buildGroupRelease(group, stichprobe, stand, 'V. Test', CLOCK)
    expect(records.map((entry) => entry.finding_id)).toEqual(['F-0003', 'F-0004'])
    expect(records.every((entry) => entry.action === 'accept')).toBe(true)
    expect(records[0].reason).toBe(releaseReason(2, 6))
    expect(records[0].by).toBe('V. Test')
    expect(records[0].at).toBe('2026-08-30T10:00:00.000Z')
  })

  it('setzt „in Arbeit", nicht „erledigt" – entschieden ist nicht umgesetzt', () => {
    const { records } = buildGroupRelease(group, stichprobe, stand, 'V. Test', CLOCK)
    expect(records.map(statusForDecision)).toEqual(['in_progress', 'in_progress'])
  })

  it('hält die geprüfte Stichprobe für `decisions.json` fest', () => {
    const { review } = buildGroupRelease(group, stichprobe, stand, 'V. Test', CLOCK)
    expect(review).toEqual({
      rule_id: 'AR-CMP-001',
      outcome: 'released',
      sampled_finding_ids: ['F-0001', 'F-0002'],
      applied_finding_ids: ['F-0003', 'F-0004'],
      blocked_by_finding_id: null,
      by: 'V. Test',
      at: '2026-08-30T10:00:00.000Z',
    })
  })
})

describe('buildGroupBlock', () => {
  it('hält fest, welches Finding die Gruppe gesperrt hat', () => {
    const [group] = groupByRule(many(3))
    expect(buildGroupBlock(group, ['F-0001', 'F-0002'], 'F-0002', 'V. Test', CLOCK)).toEqual({
      rule_id: 'AR-CMP-001',
      outcome: 'blocked',
      sampled_finding_ids: ['F-0001', 'F-0002'],
      applied_finding_ids: [],
      blocked_by_finding_id: 'F-0002',
      by: 'V. Test',
      at: '2026-08-30T10:00:00.000Z',
    })
  })
})

describe('nextSampleStep', () => {
  const stand = (overrides: Partial<ReturnType<typeof sampleProgress>>) => ({
    size: 3,
    decided: 3,
    accepted: 3,
    assigned: 0,
    rejectedId: null,
    ...overrides,
  })

  it('sperrt, sobald ein Finding der Stichprobe abgelehnt wurde', () => {
    expect(nextSampleStep(stand({ accepted: 2, rejectedId: 'F-0002' }))).toBe('blocked')
    // Auch mitten im Durchgang – die Ablehnung wartet nicht auf das Ende.
    expect(nextSampleStep(stand({ decided: 1, accepted: 0, rejectedId: 'F-0001' }))).toBe(
      'blocked',
    )
  })

  it('geht weiter, solange gezogene Findings offen sind', () => {
    expect(nextSampleStep(stand({ decided: 2, accepted: 2 }))).toBe('continue')
  })

  it('gibt erst frei, wenn jedes gezogene Finding übernommen wurde', () => {
    expect(nextSampleStep(stand({}))).toBe('release')
    expect(nextSampleStep(stand({ accepted: 2, assigned: 1 }))).toBe('incomplete')
  })
})
