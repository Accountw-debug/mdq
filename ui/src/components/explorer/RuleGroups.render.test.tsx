/**
 * Rauchtest der Regelgruppen (Aufgabe 7).
 *
 * Wie die übrigen Rauchtests ohne DOM: `renderToStaticMarkup` beantwortet, was der
 * Reducer offenlässt – steht der Leerzustand mit Erklärung da, wenn der Lauf keine
 * Massenänderung enthält, und sagt eine gesperrte Gruppe, warum sie gesperrt ist.
 */
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { load as loadYaml } from 'js-yaml'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { RuleGroups } from '@/components/explorer/RuleGroups'
import { TooltipProvider } from '@/components/ui/tooltip'
import { groupByRule } from '@/lib/sampling'
import { NO_SAMPLES, type SamplesState } from '@/state/samples'
import type { SampleReview } from '@/types/decisions-file'
import type { Finding } from '@/types/finding'

const EXAMPLES_DIR = fileURLToPath(new URL('../../../../logic/examples/findings', import.meta.url))

const examples: Finding[] = readdirSync(EXAMPLES_DIR)
  .filter((name) => name.endsWith('.yaml'))
  .sort()
  .map((name) => loadYaml(readFileSync(join(EXAMPLES_DIR, name), 'utf8')) as Finding)

function massChange(id: string, overrides: Partial<Finding> = {}): Finding {
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
    title: 'Zahlungsbedingung fehlt',
    entity: { bp_key: `C:${id}`, role: 'CUSTOMER' },
    current: { source_table: 'KNA1', source_field: 'ZTERM', value: null },
    impact_eur: { amount: '1000.00', currency: 'EUR', formula: '1 × 1.000,00 € offener Posten' },
    why: 'Grund für den Test.',
    if_wrong: 'Folge im Test.',
    remediation: { sap_transaction: 'XD02', mass_change_eligible: true },
    status: 'open',
    data_as_of: '2026-08-28',
    created_at: '2026-08-30T09:15:00Z',
    ...overrides,
  }
}

function render(
  findings: readonly Finding[],
  samples: SamplesState = NO_SAMPLES,
  reviewer = 'V. Test',
): string {
  return renderToStaticMarkup(
    <TooltipProvider>
      <RuleGroups
        groups={groupByRule(findings.filter((entry) => entry.action_type === 'mass_change'))}
        samples={samples}
        reviewer={reviewer}
        onStartSample={() => {}}
      />
    </TooltipProvider>,
  )
}

function review(overrides: Partial<SampleReview> = {}): SampleReview {
  return {
    rule_id: 'AR-CMP-001',
    outcome: 'released',
    sampled_finding_ids: ['F-0001', 'F-0002'],
    applied_finding_ids: ['F-0003'],
    blocked_by_finding_id: null,
    by: 'V. Test',
    at: '2026-08-30T10:00:00Z',
    ...overrides,
  }
}

describe('Regelgruppen im Browser-Markup', () => {
  it('erklärt den leeren Fall: die Beispiele enthalten keine Stufe A', () => {
    const html = render(examples)
    expect(html).toContain('Massenänderung setzt Stufe A voraus')
    expect(html).not.toContain('Stichprobe prüfen')
  })

  it('zeigt Gruppe, Zähler und den Knopf mit der Stichprobengröße', () => {
    const html = render([
      ...Array.from({ length: 12 }, (_, index) => massChange(`F-${index + 1}`)),
      massChange('F-99', { damage_class: 1 }),
    ])
    expect(html).toContain('AR-CMP-001')
    expect(html).toContain('Zahlungsbedingung fehlt')
    expect(html).toContain('13.000,00 €')
    expect(html).toContain('Schadensklasse 1')
    expect(html).toContain('Stichprobe prüfen')
    // Zwölf freigebbare Findings, höchstens zehn davon werden geprüft.
    expect(html).toContain('(10 von 12)')
  })

  it('sperrt den Knopf ohne Bearbeiter', () => {
    const html = render([massChange('F-1')], NO_SAMPLES, '')
    expect(html).toContain('disabled')
    expect(html).toContain('Bearbeiter')
  })

  it('nennt eine freigegebene Gruppe mit Bearbeiter und Zeitpunkt', () => {
    const html = render([massChange('F-1')], { 'AR-CMP-001': review() })
    expect(html).toContain('Freigegeben nach Stichprobe')
    expect(html).toContain('30.08.2026')
    expect(html).toContain('V. Test')
  })

  it('sagt bei einer gesperrten Gruppe, was gilt und was weiter möglich ist', () => {
    const html = render([massChange('F-1')], {
      'AR-CMP-001': review({
        outcome: 'blocked',
        applied_finding_ids: [],
        blocked_by_finding_id: 'F-0002',
      }),
    })
    expect(html).toContain('Gruppenfreigabe gesperrt')
    expect(html).toContain('F-0002')
    expect(html).toContain('einzeln entscheidbar')
    expect(html).toContain('disabled')
  })
})
