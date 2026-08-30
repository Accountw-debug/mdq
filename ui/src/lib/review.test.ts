/** Logik der Review-Karte: Sperren, Status, Entscheidungssatz, Evidenzreihenfolge. */
import { describe, expect, it } from 'vitest'
import {
  ACCEPT_BLOCKED_DAMAGE_CLASS_1,
  ACCEPT_BLOCKED_NO_OPTION,
  acceptBlockedReason,
  createDecision,
  decisionStatusLabel,
  hasRelevance,
  isOpen,
  sortEvidence,
  statusForDecision,
} from '@/lib/review'
import type { DecisionRecord } from '@/types/decision'
import type { Evidence, Finding } from '@/types/finding'

const FIXED_CLOCK = () => '2026-08-30T10:00:00.000Z'

/** Gerüst eines Findings; die Tests setzen nur, worauf sie sich beziehen. */
function finding(overrides: Partial<Finding> = {}): Finding {
  return {
    finding_id: 'F-000000000001',
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

describe('acceptBlockedReason', () => {
  it('sperrt Schadensklasse 1 – Bankdaten nie im Alleingang', () => {
    expect(acceptBlockedReason(finding({ damage_class: 1, tier: 'C' }))).toBe(
      ACCEPT_BLOCKED_DAMAGE_CLASS_1,
    )
  })

  it('verlangt bei Optionen erst eine Wahl', () => {
    const withOptions = finding({
      tier: 'decision',
      proposed: {
        value: null,
        source_summary: 'Zwei Wege',
        options: [
          { label: 'A', consequence: 'Folge A' },
          { label: 'B', consequence: 'Folge B' },
        ],
      },
    })
    expect(acceptBlockedReason(withOptions)).toBe(ACCEPT_BLOCKED_NO_OPTION)
    expect(acceptBlockedReason(withOptions, 'A')).toBeNull()
  })

  it('bleibt auch mit gewählter Option bei Schadensklasse 1 gesperrt', () => {
    const bank = finding({
      damage_class: 1,
      tier: 'decision',
      proposed: {
        value: null,
        source_summary: 'egal',
        options: [{ label: 'A', consequence: 'Folge A' }],
      },
    })
    expect(acceptBlockedReason(bank, 'A')).toBe(ACCEPT_BLOCKED_DAMAGE_CLASS_1)
  })

  it('gibt einen gewöhnlichen Vorschlag frei', () => {
    expect(acceptBlockedReason(finding())).toBeNull()
  })
})

describe('statusForDecision', () => {
  it('setzt beim Übernehmen in_progress – freigegeben ist nicht umgesetzt', () => {
    expect(statusForDecision(decision({ action: 'accept' }))).toBe('in_progress')
    expect(decisionStatusLabel(decision({ action: 'accept' }))).toBe(
      'freigegeben – Umsetzung offen',
    )
  })

  it('setzt beim Zuweisen in_progress', () => {
    expect(statusForDecision(decision({ action: 'assign', assigned_to: 'K. Meier' }))).toBe(
      'in_progress',
    )
    expect(decisionStatusLabel(decision({ action: 'assign' }))).toBe('zugewiesen')
  })

  it('trennt Ablehnung und akzeptiertes Risiko', () => {
    const rejected = decision({ action: 'reject', reason_code: 'data_correct' })
    const risk = decision({ action: 'reject', reason_code: 'accepted_risk' })
    expect(statusForDecision(rejected)).toBe('rejected')
    expect(decisionStatusLabel(rejected)).toBe('abgelehnt')
    expect(statusForDecision(risk)).toBe('accepted_risk')
    expect(decisionStatusLabel(risk)).toBe('Risiko akzeptiert')
  })

  it('vergibt nie done – das entscheidet der nächste Lauf', () => {
    for (const action of ['accept', 'reject', 'assign'] as const) {
      expect(statusForDecision(decision({ action }))).not.toBe('done')
    }
  })
})

describe('createDecision', () => {
  it('nimmt den Zeitstempel aus der übergebenen Uhr', () => {
    const record = createDecision(
      { findingId: 'F-00000000000a', action: 'accept', by: ' V. Test ' },
      FIXED_CLOCK,
    )
    expect(record.at).toBe('2026-08-30T10:00:00.000Z')
    expect(record.by).toBe('V. Test')
    expect(record.reason).toBe('Vorschlag übernommen')
    expect(record.reason_code).toBeNull()
    expect(record.assigned_to).toBeNull()
  })

  it('hält die gewählte Option als Grund fest', () => {
    const record = createDecision(
      {
        findingId: 'F-00000000000a',
        action: 'accept',
        by: 'V. Test',
        chosenOption: 'Löschvormerkung aufheben',
      },
      FIXED_CLOCK,
    )
    expect(record.reason).toBe('Option gewählt: Löschvormerkung aufheben')
  })

  it('nimmt den Freitext, wenn einer da ist – sonst den abgeleiteten Grund', () => {
    const mitText = createDecision(
      {
        findingId: 'F-00000000000a',
        action: 'reject',
        by: 'V. Test',
        reasonCode: 'intentionally_separate',
        reason: '  Konzern, zwei Konten gewollt  ',
      },
      FIXED_CLOCK,
    )
    expect(mitText.reason).toBe('Konzern, zwei Konten gewollt')

    const ohneText = createDecision(
      {
        findingId: 'F-00000000000a',
        action: 'reject',
        by: 'V. Test',
        reasonCode: 'intentionally_separate',
        reason: '   ',
      },
      FIXED_CLOCK,
    )
    expect(ohneText.reason).toBe('bewusst getrennt geführt')
    expect(ohneText.reason_code).toBe('intentionally_separate')
  })

  it('merkt sich beim Zuweisen den Empfänger', () => {
    const record = createDecision(
      { findingId: 'F-00000000000a', action: 'assign', by: 'V. Test', assignedTo: ' K. Meier ' },
      FIXED_CLOCK,
    )
    expect(record.assigned_to).toBe('K. Meier')
    expect(record.reason).toBe('Zugewiesen an K. Meier')
  })
})

describe('sortEvidence', () => {
  const entry = (reference: string, agrees: boolean): Evidence => ({
    source_type: 'deterministic',
    reference,
    value: null,
    agrees,
  })

  it('stellt Widersprüche nach vorn und lässt den Rest in Reihenfolge', () => {
    const sorted = sortEvidence([
      entry('a', true),
      entry('b', false),
      entry('c', true),
      entry('d', false),
    ])
    expect(sorted.map((e) => e.reference)).toEqual(['b', 'd', 'a', 'c'])
  })

  it('verändert die Eingabe nicht', () => {
    const input = [entry('a', true), entry('b', false)]
    sortEvidence(input)
    expect(input.map((e) => e.reference)).toEqual(['a', 'b'])
  })
})

describe('hasRelevance und isOpen', () => {
  it('erkennt einen leeren Relevanzblock', () => {
    expect(hasRelevance(finding())).toBe(false)
    expect(hasRelevance(finding({ relevance: {} }))).toBe(false)
    expect(hasRelevance(finding({ relevance: { open_items_eur: '0.00' } }))).toBe(true)
    expect(hasRelevance(finding({ relevance: { last_activity_on: '2026-08-01' } }))).toBe(true)
  })

  it('nennt nur `open` offen', () => {
    expect(isOpen(finding())).toBe(true)
    expect(isOpen(finding({ status: 'in_progress' }))).toBe(false)
    expect(isOpen(finding({ status: 'rejected' }))).toBe(false)
  })
})
