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
import type { DecisionRecord } from '@/types/decision'
import { DECISIONS_FORMAT, DECISIONS_FORMAT_VERSION } from '@/types/decisions-file'
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

function finding(findingId: string): Finding {
  return { finding_id: findingId } as Finding
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
    const file = buildDecisionsFile(RUN, state(record()), 'V. Test', CLOCK)
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
    const first = serializeDecisionsFile(buildDecisionsFile(RUN, decisions, 'V. Test', CLOCK))
    // Andere Einfügereihenfolge, gleiche Datei.
    const shuffled = state(
      record({ finding_id: 'F-e2f7b19c4d83' }),
      record({ finding_id: 'F-3a9f1c2d4e5b' }),
      record({ finding_id: 'F-c41d7e9b2a60' }),
    )
    const second = serializeDecisionsFile(buildDecisionsFile(RUN, shuffled, 'V. Test', CLOCK))
    expect(first).toBe(second)
    expect(buildDecisionsFile(RUN, decisions, 'V. Test', CLOCK).decisions.map((d) => d.finding_id)).toEqual([
      'F-3a9f1c2d4e5b',
      'F-c41d7e9b2a60',
      'F-e2f7b19c4d83',
    ])
  })

  it('benennt die Datei nach dem Lauf', () => {
    expect(decisionsFileName(RUN)).toBe('decisions-demo-2026-08-30.json')
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
    const text = serializeDecisionsFile(buildDecisionsFile(RUN, decisions, 'V. Test', CLOCK))
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
    const text = serializeDecisionsFile(buildDecisionsFile(RUN, decisions, 'V. Test', CLOCK))
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
    const text = fileJson({
      sample_reviewed: ['F-000000000001'],
      decisions: [{ ...record(), reviewed_twice: true }],
    })
    const { report } = parseDecisionsFile(text, RUN, [finding('F-000000000001')])
    expect(report.unknownFields).toEqual(['decisions[].reviewed_twice', 'sample_reviewed'])
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
