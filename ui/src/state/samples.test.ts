/** Geprüfte Stichproben der Sitzung: der Reducer neben den Entscheidungen. */
import { describe, expect, it } from 'vitest'
import { NO_SAMPLES, samplesReducer } from '@/state/samples'
import type { SampleReview } from '@/types/decisions-file'

function review(overrides: Partial<SampleReview> = {}): SampleReview {
  return {
    rule_id: 'AR-CMP-001',
    outcome: 'released',
    sampled_finding_ids: ['F-0001'],
    applied_finding_ids: ['F-0002'],
    blocked_by_finding_id: null,
    by: 'V. Test',
    at: '2026-08-30T10:00:00.000Z',
    ...overrides,
  }
}

describe('samplesReducer', () => {
  it('hält je Regel einen Ausgang', () => {
    const stand = samplesReducer(
      samplesReducer(NO_SAMPLES, { type: 'record', review: review() }),
      { type: 'record', review: review({ rule_id: 'AP-VAL-002', outcome: 'blocked' }) },
    )
    expect(Object.keys(stand).sort()).toEqual(['AP-VAL-002', 'AR-CMP-001'])
    expect(stand['AP-VAL-002'].outcome).toBe('blocked')
  })

  it('beginnt mit einem neuen Lauf ohne Stichproben', () => {
    const stand = samplesReducer(NO_SAMPLES, { type: 'record', review: review() })
    expect(samplesReducer(stand, { type: 'reset' })).toEqual(NO_SAMPLES)
    // Ohne Inhalt bleibt es dasselbe Objekt – kein unnötiges Rendern.
    expect(samplesReducer(NO_SAMPLES, { type: 'reset' })).toBe(NO_SAMPLES)
  })

  it('ersetzt beim Import, statt zu mischen', () => {
    const stand = samplesReducer(NO_SAMPLES, { type: 'record', review: review() })
    const importiert = samplesReducer(stand, {
      type: 'import',
      reviews: { 'AP-VAL-002': review({ rule_id: 'AP-VAL-002' }) },
    })
    expect(Object.keys(importiert)).toEqual(['AP-VAL-002'])
  })
})
