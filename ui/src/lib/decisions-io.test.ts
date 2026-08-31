/**
 * Tests des Entscheidungs-Vertrags (`decisions.json`).
 *
 * Die wichtigste Zusage: was das UI schreibt, liest es wieder ein – sonst ist
 * „morgen weiterarbeiten" nicht gedeckt. Dazu die Abbrüche (Regel 4: nichts stumm
 * verwerfen) und die Zusicherung, dass in keiner Meldung Geschäftspartnerdaten
 * stehen (Regel 8).
 */
import { describe, expect, it } from 'vitest'
import { LoadError } from '@/sources/findings-source'
import {
  buildDecisionsFile,
  decisionsFileName,
  describeImport,
  parseDecisionsFile,
  serializeDecisionsFile,
} from '@/lib/decisions-io'
import type { DecisionsState } from '@/state/decisions'
import { decisionsReducer } from '@/state/decisions'
import { NO_SAMPLES, type SamplesState } from '@/state/samples'
import type { DecisionRecord } from '@/types/decision'
import { DECISIONS_FORMAT, DECISIONS_FORMAT_VERSION } from '@/types/decisions-file'
import type { SampleReview } from '@/types/decisions-file'
import type { Finding, RunInfo } from '@/types/finding'

const RUN: RunInfo = {
  run_id: 'demo-2026-08-30',
  data_as_of: '2026-08-28',
  engine_version: '0.1.0',
  pack_version: '0.1',
  tables_loaded: 0,
  company_codes: ['1000'],
}

const CLOCK = () => '2026-08-30T09:15:00.000Z'

function finding(findingId: string, ruleId = 'AR-VAL-001'): Finding {
  return { finding_id: findingId, rule_id: ruleId } as Finding
}

function review(overrides: Partial<SampleReview> = {}): SampleReview {
  return {
    rule_id: 'AR-VAL-001',
    outcome: 'released',
    sampled_finding_ids: ['F-000000000001'],
    applied_finding_ids: ['F-000000000002'],
    blocked_by_finding_id: null,
    by: 'V. Test',
    at: '2026-08-30T09:14:00.000Z',
    ...overrides,
  }
}

function samples(...reviews: SampleReview[]): SamplesState {
  return Object.fromEntries(reviews.map((entry) => [entry.rule_id, entry]))
}

function record(overrides: Partial<DecisionRecord> = {}): DecisionRecord {
  return {
    finding_id: 'F-000000000001',
    action: 'accept',
    reason_code: null,
    reason: 'Vorschlag übernommen',
    assigned_to: null,
    by: 'V. Test',
    at: '2026-08-30T09:14:00.000Z',
    ...overrides,
  }
}

function state(...records: DecisionRecord[]): DecisionsState {
  return Object.fromEntries(records.map((entry) => [entry.finding_id, entry]))
}

/** Umschlag von Hand, um einzelne Felder gezielt kaputt zu machen. */
function fileJson(overrides: Record<string, unknown> = {}): string {
  return JSON.stringify({
    format: DECISIONS_FORMAT,
    format_version: DECISIONS_FORMAT_VERSION,
    run_id: RUN.run_id,
    data_as_of: RUN.data_as_of,
    engine_version: RUN.engine_version,
    pack_version: RUN.pack_version,
    exported_at: '2026-08-30T09:15:00.000Z',
    exported_by: 'V. Test',
    decisions: [record()],
    ...overrides,
  })
}

describe('buildDecisionsFile', () => {
  it('trägt Format, Version und den Lauf-Kopf', () => {
    const file = buildDecisionsFile(RUN, state(record()), NO_SAMPLES, 'V. Test', CLOCK)
    expect(file.format).toBe(DECISIONS_FORMAT)
    expect(file.format_version).toBe(DECISIONS_FORMAT_VERSION)
    expect(file.run_id).toBe('demo-2026-08-30')
    expect(file.data_as_of).toBe('2026-08-28')
    expect(file.engine_version).toBe('0.1.0')
    expect(file.pack_version).toBe('0.1')
    expect(file.exported_at).toBe('2026-08-30T09:15:00.000Z')
  })

  it('sortiert nach finding_id – gleicher Stand, gleiche Datei (Regel 9)', () => {
    const decisions = state(
      record({ finding_id: 'F-c41d7e9b2a60' }),
      record({ finding_id: 'F-3a9f1c2d4e5b' }),
      record({ finding_id: 'F-e2f7b19c4d83' }),
    )
    const first = serializeDecisionsFile(buildDecisionsFile(RUN, decisions, NO_SAMPLES, 'V. Test', CLOCK))
    // Andere Einfügereihenfolge, gleiche Datei.
    const shuffled = state(
      record({ finding_id: 'F-e2f7b19c4d83' }),
      record({ finding_id: 'F-3a9f1c2d4e5b' }),
      record({ finding_id: 'F-c41d7e9b2a60' }),
    )
    const second = serializeDecisionsFile(buildDecisionsFile(RUN, shuffled, NO_SAMPLES, 'V. Test', CLOCK))
    expect(first).toBe(second)
    expect(buildDecisionsFile(RUN, decisions, NO_SAMPLES, 'V. Test', CLOCK).decisions.map((d) => d.finding_id)).toEqual([
      'F-3a9f1c2d4e5b',
      'F-c41d7e9b2a60',
      'F-e2f7b19c4d83',
    ])
  })

  it('benennt die Datei nach dem Lauf', () => {
    expect(decisionsFileName(RUN)).toBe('decisions-demo-2026-08-30.json')
  })
})

describe('Stichproben im Vertrag (`sample_reviewed`)', () => {
  it('schreibt das Feld erst, wenn eine Stichprobe geprüft wurde', () => {
    const ohne = buildDecisionsFile(RUN, state(record()), NO_SAMPLES, 'V. Test', CLOCK)
    expect(ohne.sample_reviewed).toBeUndefined()

    const mit = buildDecisionsFile(RUN, state(record()), samples(review()), 'V. Test', CLOCK)
    expect(mit.sample_reviewed).toHaveLength(1)
  })

  it('liest zurück, was geschrieben wurde – Freigabe wie Sperre', () => {
    const geprueft = samples(
      review(),
      review({
        rule_id: 'AP-VAL-002',
        outcome: 'blocked',
        applied_finding_ids: [],
        blocked_by_finding_id: 'F-000000000003',
      }),
    )
    const text = serializeDecisionsFile(
      buildDecisionsFile(RUN, state(record()), geprueft, 'V. Test', CLOCK),
    )
    const { samples: gelesen, report } = parseDecisionsFile(text, RUN, [
      finding('F-000000000001'),
      finding('F-000000000003', 'AP-VAL-002'),
    ])
    expect(gelesen).toEqual(geprueft)
    expect(report.samplesTotal).toBe(2)
    expect(report.samplesApplied).toBe(2)
    expect(report.missingSampleRules).toEqual([])
  })

  it('nennt Stichproben zu Regeln, die der Lauf nicht kennt (Regel 4)', () => {
    const text = serializeDecisionsFile(
      buildDecisionsFile(
        RUN,
        state(record()),
        samples(review({ rule_id: 'ZZ-XXX-009' })),
        'V. Test',
        CLOCK,
      ),
    )
    const { samples: gelesen, report } = parseDecisionsFile(text, RUN, [
      finding('F-000000000001'),
    ])
    expect(gelesen).toEqual({})
    expect(report.missingSampleRules).toEqual(['ZZ-XXX-009'])
    expect(describeImport(report)).toContain(
      '0 von 1 geprüften Stichproben übernommen.',
    )
    expect(describeImport(report)).toContain('Ohne Regel im geladenen Lauf: ZZ-XXX-009')
  })

  it('bricht bei unbekanntem outcome ab, statt die Sperre zu verlieren', () => {
    const text = fileJson({ sample_reviewed: [{ ...review(), outcome: 'irgendwas' }] })
    expect(() => parseDecisionsFile(text, RUN, [finding('F-000000000001')])).toThrow(LoadError)
  })

  it('bricht bei doppelter rule_id ab', () => {
    const text = fileJson({ sample_reviewed: [review(), review()] })
    expect(() => parseDecisionsFile(text, RUN, [finding('F-000000000001')])).toThrow(
      /rule_id kommt in sample_reviewed doppelt vor/,
    )
  })

  it('nennt unbekannte Felder eines Stichproben-Satzes, statt sie stumm zu schlucken', () => {
    const text = fileJson({ sample_reviewed: [{ ...review(), erfunden: true }] })
    const { report } = parseDecisionsFile(text, RUN, [finding('F-000000000001')])
    expect(report.unknownFields).toContain('sample_reviewed[].erfunden')
  })
})

describe('Rundlauf Export → Import', () => {
  it('liest zurück, was geschrieben wurde – Satz für Satz', () => {
    const decisions = state(
      record({ finding_id: 'F-000000000001' }),
      record({
        finding_id: 'F-000000000002',
        action: 'reject',
        reason_code: 'data_correct',
        reason: 'Daten sind korrekt',
      }),
      record({
        finding_id: 'F-000000000003',
        action: 'assign',
        reason: 'Zugewiesen an Team Stammdaten',
        assigned_to: 'Team Stammdaten',
      }),
    )
    const text = serializeDecisionsFile(buildDecisionsFile(RUN, decisions, NO_SAMPLES, 'V. Test', CLOCK))
    const findings = [
      finding('F-000000000001'),
      finding('F-000000000002'),
      finding('F-000000000003'),
    ]
    const { records, report } = parseDecisionsFile(text, RUN, findings)
    expect(records).toEqual(decisions)
    expect(report.applied).toBe(3)
    expect(report.total).toBe(3)
    expect(report.missing).toEqual([])
    expect(report.runMismatch).toBeNull()
    expect(report.exportedBy).toBe('V. Test')
  })

  it('stellt den Stand der Sitzung über den Reducer wieder her', () => {
    const decisions = state(record(), record({ finding_id: 'F-000000000002' }))
    const text = serializeDecisionsFile(buildDecisionsFile(RUN, decisions, NO_SAMPLES, 'V. Test', CLOCK))
    const { records } = parseDecisionsFile(text, RUN, [
      finding('F-000000000001'),
      finding('F-000000000002'),
    ])
    // Import ersetzt, er mischt nicht.
    const before = state(record({ finding_id: 'F-999999999999' }))
    expect(decisionsReducer(before, { type: 'import', records })).toEqual(decisions)
  })
})

describe('parseDecisionsFile – Abbrüche', () => {
  it('meldet ungültiges JSON', () => {
    expect(() => parseDecisionsFile('{', RUN, [])).toThrow(LoadError)
  })

  it('lehnt eine fremde Datei ab', () => {
    expect(() => parseDecisionsFile(fileJson({ format: 'irgendwas' }), RUN, [])).toThrow(
      /format/,
    )
  })

  it('lehnt eine unbekannte Version ab, statt zu raten', () => {
    expect(() => parseDecisionsFile(fileJson({ format_version: 99 }), RUN, [])).toThrow(
      /format_version/,
    )
  })

  it('meldet eine fehlende Entscheidungsliste', () => {
    expect(() => parseDecisionsFile(fileJson({ decisions: null }), RUN, [])).toThrow(
      /decisions/,
    )
  })

  it('meldet eine unbekannte Aktion mit finding_id', () => {
    const text = fileJson({ decisions: [record({ action: 'loeschen' as never })] })
    expect(() => parseDecisionsFile(text, RUN, [])).toThrow(
      /F-000000000001: unbekannte Aktion/,
    )
  })

  it('meldet einen unbekannten reason_code', () => {
    const text = fileJson({ decisions: [record({ reason_code: 'egal' as never })] })
    expect(() => parseDecisionsFile(text, RUN, [])).toThrow(/reason_code/)
  })

  it('besteht auf einem UTC-Zeitstempel', () => {
    const text = fileJson({ decisions: [record({ at: '2026-08-30T09:14:00+02:00' })] })
    expect(() => parseDecisionsFile(text, RUN, [])).toThrow(/UTC-Zeitstempel/)
  })

  it('meldet ein fehlendes Pflichtfeld mit Feldnamen', () => {
    const broken = { ...record() } as Record<string, unknown>
    delete broken.by
    expect(() => parseDecisionsFile(fileJson({ decisions: [broken] }), RUN, [])).toThrow(/by/)
  })

  it('meldet doppelte finding_id', () => {
    const text = fileJson({ decisions: [record(), record()] })
    expect(() => parseDecisionsFile(text, RUN, [])).toThrow(/doppelt/)
  })

  it('nennt in Meldungen keine Geschäftspartnerdaten', () => {
    const text = fileJson({
      decisions: [
        record({
          action: 'loeschen' as never,
          reason: 'Müller Maschinenbau GmbH ist korrekt',
        }),
      ],
    })
    try {
      parseDecisionsFile(text, RUN, [])
      expect.unreachable('sollte werfen')
    } catch (error) {
      expect((error as Error).message).toContain('F-000000000001')
      expect((error as Error).message).not.toContain('Müller')
    }
  })
})

describe('parseDecisionsFile – Bericht statt Abbruch', () => {
  it('übernimmt nur Entscheidungen mit Finding im geladenen Lauf', () => {
    const text = fileJson({
      decisions: [record(), record({ finding_id: 'F-000000000002' })],
    })
    const { records, report } = parseDecisionsFile(text, RUN, [finding('F-000000000001')])
    expect(Object.keys(records)).toEqual(['F-000000000001'])
    expect(report.applied).toBe(1)
    expect(report.total).toBe(2)
    expect(report.missing).toEqual(['F-000000000002'])
  })

  it('warnt bei einem anderen Lauf, statt abzubrechen', () => {
    const text = fileJson({ run_id: 'demo-2026-08-29' })
    const { records, report } = parseDecisionsFile(text, RUN, [finding('F-000000000001')])
    expect(Object.keys(records)).toHaveLength(1)
    expect(report.runMismatch).toEqual({
      file: 'demo-2026-08-29',
      loaded: 'demo-2026-08-30',
    })
  })

  it('nennt unbekannte Felder, statt sie stumm zu verwerfen (Regel 4)', () => {
    // `sample_reviewed` stand hier, solange das Feld reserviert war; seit Aufgabe 7
    // liest der Vertrag es, also braucht der Test ein anderes fremdes Feld.
    const text = fileJson({
      spaeter_erfunden: ['F-000000000001'],
      decisions: [{ ...record(), reviewed_twice: true }],
    })
    const { report } = parseDecisionsFile(text, RUN, [finding('F-000000000001')])
    expect(report.unknownFields).toEqual(['decisions[].reviewed_twice', 'spaeter_erfunden'])
  })
})

describe('describeImport', () => {
  it('beginnt mit den Zahlen: übernommen und ohne Finding', () => {
    const text = fileJson({
      decisions: [record(), record({ finding_id: 'F-000000000002' })],
    })
    const { report } = parseDecisionsFile(text, RUN, [finding('F-000000000001')])
    const lines = describeImport(report)
    expect(lines[0]).toBe(
      '1 von 2 Entscheidungen übernommen; 1 ohne Finding im geladenen Lauf.',
    )
    expect(lines[1]).toContain('F-000000000002')
  })

  it('sagt es, wenn die Datei zu einem anderen Lauf gehört', () => {
    const { report } = parseDecisionsFile(fileJson({ run_id: 'demo-2026-08-29' }), RUN, [
      finding('F-000000000001'),
    ])
    expect(describeImport(report).join(' ')).toContain('demo-2026-08-29')
  })

  it('bleibt bei einem sauberen Import einzeilig', () => {
    const { report } = parseDecisionsFile(fileJson(), RUN, [finding('F-000000000001')])
    expect(describeImport(report)).toHaveLength(1)
  })
})
