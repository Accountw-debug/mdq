/**
 * Tests für Filter, Suche, Sortierung und Zähler des Explorers.
 *
 * Die Logik wird an gebauten Findings geprüft; die Akzeptanzkriterien aus
 * `docs/specs/SPRINT-5-UI.md` (richtige Tabs, Standardsortierung) zusätzlich an den
 * sechs Beispielen aus `logic/examples/findings/`. Die werden nur gelesen.
 */
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { load as loadYaml } from 'js-yaml'
import { describe, expect, it } from 'vitest'
import {
  ALL,
  DEFAULT_SORT,
  EMPTY_FILTERS,
  NO_COMPANY_CODE,
  companyCodeOptions,
  countByActionType,
  impactCents,
  indexOfId,
  selectVisibleFindings,
  sortFindings,
  startTab,
} from '@/lib/select-findings'
import type { Filters } from '@/lib/select-findings'
import type { Finding } from '@/types/finding'

const EXAMPLES_DIR = fileURLToPath(new URL('../../../logic/examples/findings', import.meta.url))

function loadExamples(): Finding[] {
  return readdirSync(EXAMPLES_DIR)
    .filter((name) => name.endsWith('.yaml'))
    .sort()
    .map((name) => loadYaml(readFileSync(join(EXAMPLES_DIR, name), 'utf8')) as Finding)
}

const examples = loadExamples()

/** Minimal befülltes Finding; jeder Test überschreibt nur, worum es ihm geht. */
function makeFinding(overrides: Partial<Finding> & { finding_id: string }): Finding {
  return {
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
    title: 'Beispiel',
    entity: { bp_key: 'C:0000100001', role: 'CUSTOMER', company_code: '1000' },
    current: { source_table: 'KNA1', source_field: 'STCEG', value: null },
    why: 'warum',
    if_wrong: 'wenn falsch',
    remediation: { sap_transaction: 'XD02', mass_change_eligible: false },
    status: 'open',
    data_as_of: '2026-08-28',
    created_at: '2026-08-30T09:15:00Z',
    ...overrides,
  } as Finding
}

function withFilters(overrides: Partial<Filters>): Filters {
  return { ...EMPTY_FILTERS, ...overrides }
}

function ids(findings: readonly Finding[]): string[] {
  return findings.map((finding) => finding.finding_id)
}

describe('sortFindings', () => {
  it('sortiert nach Euro-Wirkung absteigend, dann Schwere, dann finding_id', () => {
    const findings = [
      makeFinding({ finding_id: 'F-000000000003', severity: 'low' }),
      makeFinding({
        finding_id: 'F-000000000001',
        impact_eur: { amount: '100.00', currency: 'EUR', formula: '100' },
      }),
      makeFinding({ finding_id: 'F-000000000002', severity: 'critical' }),
      makeFinding({
        finding_id: 'F-000000000004',
        impact_eur: { amount: '32000.00', currency: 'EUR', formula: '32000' },
      }),
    ]
    expect(ids(sortFindings(findings))).toEqual([
      'F-000000000004',
      'F-000000000001',
      'F-000000000002',
      'F-000000000003',
    ])
  })

  it('vergleicht Beträge als Cents, nicht als Text', () => {
    const findings = [
      makeFinding({
        finding_id: 'F-00000000000a',
        impact_eur: { amount: '9.00', currency: 'EUR', formula: '9' },
      }),
      makeFinding({
        finding_id: 'F-00000000000b',
        impact_eur: { amount: '100.00', currency: 'EUR', formula: '100' },
      }),
    ]
    expect(ids(sortFindings(findings))).toEqual(['F-00000000000b', 'F-00000000000a'])
  })

  it('behandelt Findings ohne Euro-Wirkung als 0 und stellt sie hinten an', () => {
    const ohne = makeFinding({ finding_id: 'F-00000000000c' })
    expect(impactCents(ohne)).toBe(0n)
    const mit = makeFinding({
      finding_id: 'F-00000000000d',
      impact_eur: { amount: '0.01', currency: 'EUR', formula: '0.01' },
    })
    expect(ids(sortFindings([ohne, mit]))).toEqual(['F-00000000000d', 'F-00000000000c'])
  })

  it('ist stabil: dieselbe Liste in anderer Reihenfolge ergibt dieselbe Ausgabe', () => {
    const findings = [
      makeFinding({ finding_id: 'F-00000000000e' }),
      makeFinding({ finding_id: 'F-00000000000f' }),
      makeFinding({ finding_id: 'F-000000000010' }),
    ]
    expect(ids(sortFindings(findings))).toEqual(ids(sortFindings([...findings].reverse())))
  })

  it('dreht die Richtung um, ohne den Gleichstand dem Zufall zu überlassen', () => {
    const findings = [
      makeFinding({ finding_id: 'F-000000000012', rule_id: 'AP-LEA-002' }),
      makeFinding({ finding_id: 'F-000000000011', rule_id: 'AP-LEA-001' }),
    ]
    expect(ids(sortFindings(findings, { column: 'rule_id', direction: 'asc' }))).toEqual([
      'F-000000000011',
      'F-000000000012',
    ])
    expect(ids(sortFindings(findings, { column: 'rule_id', direction: 'desc' }))).toEqual([
      'F-000000000012',
      'F-000000000011',
    ])
  })
})

describe('Filter', () => {
  const findings = [
    makeFinding({ finding_id: 'F-000000000021', side: 'AR', severity: 'high' }),
    makeFinding({
      finding_id: 'F-000000000022',
      side: 'AP',
      severity: 'high',
      entity: { bp_key: 'V:0000200845', role: 'VENDOR', company_code: '2000' },
    }),
    makeFinding({
      finding_id: 'F-000000000023',
      side: 'AP',
      severity: 'low',
      entity: { bp_key: 'V:0000200117', role: 'VENDOR' },
    }),
  ]

  function visible(filters: Filters, search = ''): string[] {
    return ids(
      selectVisibleFindings(findings, { tab: 'review', filters, search, sort: DEFAULT_SORT }),
    )
  }

  it('lässt ohne Filter alles durch', () => {
    expect(visible(EMPTY_FILTERS)).toHaveLength(3)
  })

  it('filtert je Dimension einwertig', () => {
    expect(visible(withFilters({ side: 'AP' }))).toEqual(['F-000000000022', 'F-000000000023'])
    expect(visible(withFilters({ severity: 'low' }))).toEqual(['F-000000000023'])
  })

  it('verknüpft mehrere Dimensionen mit UND', () => {
    expect(visible(withFilters({ side: 'AP', severity: 'high' }))).toEqual(['F-000000000022'])
    expect(visible(withFilters({ side: 'AR', severity: 'low' }))).toEqual([])
  })

  it('findet Findings ohne Buchungskreis unter „ohne Buchungskreis"', () => {
    expect(visible(withFilters({ companyCode: NO_COMPANY_CODE }))).toEqual(['F-000000000023'])
    expect(visible(withFilters({ companyCode: '2000' }))).toEqual(['F-000000000022'])
  })

  it('bietet Buchungskreise sortiert an, den Sammeleintrag zuletzt', () => {
    expect(companyCodeOptions(findings)).toEqual(['1000', '2000', NO_COMPANY_CODE])
    expect(companyCodeOptions([findings[0]])).toEqual(['1000'])
  })
})

describe('Suche', () => {
  const findings = [
    makeFinding({
      finding_id: 'F-000000000031',
      title: 'USt-ID-Präfix passt nicht zum Sitzland',
      rule_id: 'AR-VAL-001',
      entity: {
        bp_key: 'C:0000100234',
        role: 'CUSTOMER',
        display_name: 'Müller Maschinenbau GmbH',
        company_code: '1000',
      },
    }),
    makeFinding({
      finding_id: 'F-000000000032',
      title: 'Skontoverlust 12 Monate',
      rule_id: 'AP-LEA-002',
      entity: { bp_key: 'V:0000200117', role: 'VENDOR', company_code: '1000' },
    }),
  ]

  function search(needle: string): string[] {
    return ids(
      selectVisibleFindings(findings, {
        tab: 'review',
        filters: EMPTY_FILTERS,
        search: needle,
        sort: DEFAULT_SORT,
      }),
    )
  }

  it('sucht über bp_key, display_name, Titel und Regel-ID', () => {
    expect(search('0000100234')).toEqual(['F-000000000031'])
    expect(search('müller')).toEqual(['F-000000000031'])
    expect(search('Skontoverlust')).toEqual(['F-000000000032'])
    expect(search('AP-LEA')).toEqual(['F-000000000032'])
  })

  it('ignoriert Groß- und Kleinschreibung und umschließende Leerzeichen', () => {
    expect(search('  MASCHINENBAU  ')).toEqual(['F-000000000031'])
  })

  it('liefert bei leerer Suche alles', () => {
    expect(search('')).toHaveLength(2)
  })
})

describe('Tab-Zähler', () => {
  it('zählt jeden Aktionstyp, auch mit 0', () => {
    const counts = countByActionType(
      [
        makeFinding({ finding_id: 'F-000000000041', action_type: 'review' }),
        makeFinding({ finding_id: 'F-000000000042', action_type: 'decision' }),
      ],
      EMPTY_FILTERS,
      '',
    )
    expect(counts).toEqual({ mass_change: 0, review: 1, decision: 1, process: 0 })
  })

  it('zählt nach Filter und Suche, damit Zahl und Tabelle zusammenpassen', () => {
    const findings = [
      makeFinding({ finding_id: 'F-000000000051', action_type: 'review', side: 'AR' }),
      makeFinding({ finding_id: 'F-000000000052', action_type: 'review', side: 'AP' }),
    ]
    expect(countByActionType(findings, withFilters({ side: 'AP' }), '').review).toBe(1)
    expect(countByActionType(findings, EMPTY_FILTERS, 'gibtesnicht').review).toBe(0)
  })
})

describe('startTab', () => {
  it('öffnet auf Review, solange der Lauf keine Massenänderung hat', () => {
    const findings = [
      makeFinding({ finding_id: 'F-1', action_type: 'review' }),
      makeFinding({ finding_id: 'F-2', action_type: 'decision' }),
    ]
    expect(startTab(findings)).toBe('review')
    // Auch an den sechs Beispielen: sie enthalten keine Stufe A.
    expect(startTab(examples)).toBe('review')
  })

  it('öffnet auf Massenänderung, sobald der Lauf eine Stufe-A-Gruppe hat', () => {
    const findings = [
      makeFinding({ finding_id: 'F-1', action_type: 'review' }),
      makeFinding({ finding_id: 'F-2', action_type: 'process' }),
      makeFinding({ finding_id: 'F-3', tier: 'A', action_type: 'mass_change' }),
    ]
    expect(startTab(findings)).toBe('mass_change')
  })

  it('öffnet einen leeren Lauf auf Review', () => {
    expect(startTab([])).toBe('review')
  })
})

describe('indexOfId', () => {
  it('findet die Position in der sichtbaren Liste', () => {
    const visible = selectVisibleFindings(examples, {
      tab: 'review',
      filters: EMPTY_FILTERS,
      search: '',
      sort: DEFAULT_SORT,
    })
    expect(indexOfId(visible, 'F-e2f7b19c4d83')).toBe(1)
  })

  it('meldet -1 für ein herausgefiltertes und für gar kein Finding', () => {
    const visible = selectVisibleFindings(examples, {
      tab: 'review',
      filters: withFilters({ companyCode: '2000' }),
      search: '',
      sort: DEFAULT_SORT,
    })
    expect(indexOfId(visible, 'F-c41d7e9b2a60')).toBe(-1)
    expect(indexOfId(visible, null)).toBe(-1)
  })
})

describe('die sechs Beispiel-Findings', () => {
  it('werden vollständig gelesen', () => {
    expect(examples).toHaveLength(6)
  })

  it('verteilen sich auf die Tabs wie im Lauf angelegt', () => {
    expect(countByActionType(examples, EMPTY_FILTERS, '')).toEqual({
      mass_change: 0,
      review: 4,
      decision: 1,
      process: 1,
    })
  })

  it('stehen im Tab Review nach Euro-Wirkung absteigend', () => {
    const visible = selectVisibleFindings(examples, {
      tab: 'review',
      filters: EMPTY_FILTERS,
      search: '',
      sort: DEFAULT_SORT,
    })
    expect(ids(visible)).toEqual([
      'F-c41d7e9b2a60',
      'F-e2f7b19c4d83',
      'F-3a9f1c2d4e5b',
      'F-7b2e8c1d9a3f',
    ])
  })

  it('kennen die Buchungskreise 1000 und 2000 sowie ein Finding ohne', () => {
    expect(companyCodeOptions(examples)).toEqual(['1000', '2000', NO_COMPANY_CODE])
  })

  it('lassen sich über den Buchungskreis-Filter einschränken', () => {
    const visible = selectVisibleFindings(examples, {
      tab: 'review',
      filters: withFilters({ companyCode: '2000' }),
      search: '',
      sort: DEFAULT_SORT,
    })
    expect(ids(visible)).toEqual(['F-e2f7b19c4d83'])
  })

  it('kennt ALL als Wert, der nicht einschränkt', () => {
    expect(EMPTY_FILTERS.side).toBe(ALL)
  })
})
