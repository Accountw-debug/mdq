/**
 * Kennzahlen des Dashboards gegen die sechs Beispiel-Findings.
 *
 * Die Summe steht in der Spec (Sprint 5, Aufgabe 6): 32.000 + 8.930 + 4.812,40 +
 * 27.300 = 73.042,40 €. Sie wird hier nicht nachgerechnet, sondern behauptet – ein
 * erwartetes Ergebnis wird nie an das Programm angepasst (CLAUDE.md, Regel 1).
 */
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { load as loadYaml } from 'js-yaml'
import { describe, expect, it } from 'vitest'
import { TOP_COUNT, summarize } from '@/lib/dashboard'
import type { Finding } from '@/types/finding'

const EXAMPLES_DIR = fileURLToPath(new URL('../../../logic/examples/findings', import.meta.url))

const examples: Finding[] = readdirSync(EXAMPLES_DIR)
  .filter((name) => name.endsWith('.yaml'))
  .sort()
  .map((name) => loadYaml(readFileSync(join(EXAMPLES_DIR, name), 'utf8')) as Finding)

/** Kopie eines Beispiels mit geänderten Feldern – die Beispiele selbst bleiben unberührt. */
function variant(base: Finding, changes: Partial<Finding>): Finding {
  return { ...base, ...changes }
}

/** Grundlage der synthetischen Fälle: ein Beispiel, das eine Euro-Wirkung trägt. */
const WITH_IMPACT = examples.find((finding) => finding.impact_eur != null)
if (WITH_IMPACT?.impact_eur == null) throw new Error('Beispiel mit Euro-Wirkung fehlt')
const BASE_IMPACT = WITH_IMPACT.impact_eur

describe('Zähler', () => {
  it('zählt die sechs Beispiele, alle offen', () => {
    const summary = summarize(examples)
    expect(summary.total).toBe(6)
    expect(summary.open).toBe(6)
    expect(summary.decided).toBe(0)
  })

  it('zählt ein entschiedenes Finding nicht mehr als offen', () => {
    const decided = examples.map((finding, index) =>
      index === 0 ? variant(finding, { status: 'rejected' }) : finding,
    )
    const summary = summarize(decided)
    expect(summary.open).toBe(5)
    expect(summary.decided).toBe(1)
  })
})

describe('Euro-Wirkung', () => {
  it('summiert die vier Beträge zu 73.042,40 EUR', () => {
    const summary = summarize(examples)
    expect(summary.totals).toEqual([{ currency: 'EUR', amount: '73042.40' }])
  })

  it('benennt die beiden Findings ohne Euro-Wirkung', () => {
    expect(summarize(examples).withoutImpact).toBe(2)
  })

  it('summiert Währungen getrennt und rechnet nichts um', () => {
    const chf = variant(WITH_IMPACT, {
      finding_id: 'F-0000000000ff',
      impact_eur: { ...BASE_IMPACT, amount: '1000.00', currency: 'CHF' },
    })
    const summary = summarize([...examples, chf])
    expect(summary.totals).toEqual([
      { currency: 'EUR', amount: '73042.40' },
      { currency: 'CHF', amount: '1000.00' },
    ])
  })
})

describe('Kategorien', () => {
  it('führt jede vorkommende Kategorie mit ihrer Summe, absteigend', () => {
    const summary = summarize(examples)
    expect(summary.byCategory).toEqual([
      {
        category: 'leakage',
        count: 2,
        totals: [{ currency: 'EUR', amount: '36812.40' }],
        withoutImpact: 0,
      },
      {
        category: 'validity',
        count: 2,
        totals: [{ currency: 'EUR', amount: '27300.00' }],
        withoutImpact: 1,
      },
      {
        category: 'consistency',
        count: 1,
        totals: [{ currency: 'EUR', amount: '8930.00' }],
        withoutImpact: 0,
      },
      { category: 'duplicate', count: 1, totals: [], withoutImpact: 1 },
    ])
  })

  it('sortiert Kategorien ohne Euro-Wirkung nach Name, nicht nach Zufall', () => {
    const [first] = examples
    const plain = [
      variant(first, { finding_id: 'F-000000000002', category: 'risk', impact_eur: null }),
      variant(first, { finding_id: 'F-000000000001', category: 'hygiene', impact_eur: null }),
    ]
    expect(summarize(plain).byCategory.map((entry) => entry.category)).toEqual([
      'hygiene',
      'risk',
    ])
  })
})

describe('Verteilung nach Stufe', () => {
  it('nennt alle vier Stufen in fester Reihenfolge, auch die leere', () => {
    expect(summarize(examples).byTier).toEqual([
      { tier: 'A', count: 0 },
      { tier: 'B', count: 3 },
      { tier: 'C', count: 2 },
      { tier: 'decision', count: 1 },
    ])
  })
})

describe('Top-Liste', () => {
  it('listet nur Findings mit Euro-Wirkung, absteigend', () => {
    const summary = summarize(examples)
    expect(summary.top.map((finding) => finding.impact_eur?.amount)).toEqual([
      '32000.00',
      '27300.00',
      '8930.00',
      '4812.40',
    ])
  })

  it('kürzt auf zehn Einträge', () => {
    const many = Array.from({ length: 14 }, (_, index) =>
      variant(WITH_IMPACT, {
        finding_id: `F-0000000000${index.toString(16).padStart(2, '0')}`,
        impact_eur: { ...BASE_IMPACT, amount: `${100 + index}.00` },
      }),
    )
    const summary = summarize(many)
    expect(summary.top).toHaveLength(TOP_COUNT)
    expect(summary.top[0].impact_eur?.amount).toBe('113.00')
  })

  it('entscheidet den Gleichstand über die finding_id', () => {
    const pair = [
      variant(WITH_IMPACT, { finding_id: 'F-00000000000b' }),
      variant(WITH_IMPACT, { finding_id: 'F-00000000000a' }),
    ]
    expect(summarize(pair).top.map((finding) => finding.finding_id)).toEqual([
      'F-00000000000a',
      'F-00000000000b',
    ])
  })
})

describe('Leerer Lauf', () => {
  it('liefert Nullen statt geschätzter Zahlen', () => {
    const summary = summarize([])
    expect(summary.total).toBe(0)
    expect(summary.open).toBe(0)
    expect(summary.totals).toEqual([])
    expect(summary.byCategory).toEqual([])
    expect(summary.top).toEqual([])
    expect(summary.byTier.every((entry) => entry.count === 0)).toBe(true)
  })
})
