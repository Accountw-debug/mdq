/**
 * Tests der Prüfungen, durch die jede `FindingsSource` ihre Daten führt: eine
 * unbrauchbare Datei muss auffallen, statt halb dargestellt zu werden
 * (CLAUDE.md, Regel 4).
 */
import { describe, expect, it } from 'vitest'
import { deriveRun, parseFindings } from '@/sources/parse'
import { LoadError } from '@/sources/findings-source'
import type { Finding } from '@/types/finding'

function findingJson(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    finding_id: 'F-000000000001',
    run_id: 'demo-2026-08-30',
    rule_id: 'AR-VAL-001',
    rule_version: '1',
    engine_version: '0.1.0',
    pack_version: '0.1',
    side: 'AR',
    category: 'validity',
    severity: 'medium',
    damage_class: 3,
    tier: 'B',
    action_type: 'review',
    entity: { bp_key: 'C:0000100001', role: 'CUSTOMER', company_code: '1000' },
    current: { source_table: 'KNA1', source_field: 'STCEG', value: null },
    why: 'warum',
    if_wrong: 'wenn falsch',
    remediation: { sap_transaction: 'XD02', mass_change_eligible: false },
    status: 'open',
    data_as_of: '2026-08-28',
    created_at: '2026-08-30T09:15:00Z',
    ...overrides,
  }
}

describe('parseFindings', () => {
  it('liest ein Array von Findings', () => {
    expect(parseFindings(JSON.stringify([findingJson()]))).toHaveLength(1)
  })

  it('liest auch ein Objekt mit dem Schlüssel findings', () => {
    expect(parseFindings(JSON.stringify({ findings: [findingJson()] }))).toHaveLength(1)
  })

  it('meldet ungültiges JSON', () => {
    expect(() => parseFindings('{')).toThrow(LoadError)
  })

  it('meldet eine leere Datei, statt einen leeren Explorer zu zeigen', () => {
    expect(() => parseFindings('[]')).toThrow(/keine Findings/)
  })

  it('meldet ein fehlendes Pflichtfeld mit Feldnamen', () => {
    const broken = findingJson()
    delete broken.action_type
    expect(() => parseFindings(JSON.stringify([broken]))).toThrow(/action_type/)
  })

  it('meldet einen unbekannten Aktionstyp', () => {
    expect(() =>
      parseFindings(JSON.stringify([findingJson({ action_type: 'irgendwas' })])),
    ).toThrow(/Aktionstyp/)
  })

  it('meldet doppelte finding_id', () => {
    expect(() => parseFindings(JSON.stringify([findingJson(), findingJson()]))).toThrow(
      /doppelt/,
    )
  })

  it('nennt in Meldungen keine Geschäftspartnerdaten', () => {
    const broken = findingJson({
      entity: { role: 'CUSTOMER', display_name: 'Müller Maschinenbau GmbH' },
    })
    try {
      parseFindings(JSON.stringify([broken]))
      expect.unreachable('sollte werfen')
    } catch (error) {
      expect((error as Error).message).toContain('entity.bp_key')
      expect((error as Error).message).not.toContain('Müller')
    }
  })
})

describe('deriveRun', () => {
  it('leitet Lauf-Kopf und Buchungskreise ab', () => {
    const findings = parseFindings(
      JSON.stringify([
        findingJson(),
        findingJson({
          finding_id: 'F-000000000002',
          entity: { bp_key: 'V:0000200845', role: 'VENDOR', company_code: '2000' },
        }),
        findingJson({
          finding_id: 'F-000000000003',
          entity: { bp_key: 'V:0000200117', role: 'VENDOR' },
        }),
      ]),
    )
    expect(deriveRun(findings)).toEqual({
      run_id: 'demo-2026-08-30',
      data_as_of: '2026-08-28',
      engine_version: '0.1.0',
      pack_version: '0.1',
      // Das UI kennt die Ladeschicht nicht; die echte Zahl kommt aus run.json der Engine.
      tables_loaded: 0,
      company_codes: ['1000', '2000'],
    })
  })

  it('lehnt Findings aus verschiedenen Läufen ab', () => {
    const findings = [
      findingJson(),
      findingJson({ finding_id: 'F-000000000002', run_id: 'demo-2026-08-31' }),
    ] as unknown as Finding[]
    expect(() => deriveRun(findings)).toThrow(/run_id/)
  })
})
