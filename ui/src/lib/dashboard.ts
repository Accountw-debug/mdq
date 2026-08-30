/**
 * Kennzahlen des Dashboards – reine Funktionen ohne React.
 *
 * Gerechnet wird über `bigint`-Cents, nie über `Number` (CLAUDE.md, Regel 2), und
 * jede Summe trägt ihre Währung: Beträge verschiedener Währungen werden nebeneinander
 * ausgewiesen und nie umgerechnet (Freigabe Victor, 2026-08-30). Jede Reihenfolge
 * endet auf einem eindeutigen Schlüssel, damit derselbe Lauf immer dasselbe
 * Dashboard ergibt (Regel 9).
 */

import { centsToAmount, parseCents } from '@/lib/format'
import { isOpen } from '@/lib/review'
import { sortFindings } from '@/lib/select-findings'
import type { Category, Finding, Tier } from '@/types/finding'
import { TIERS } from '@/types/finding'

/** Ein Betrag mit seiner Währung – ohne sie ist eine Summe nicht lesbar (Regel 2). */
export interface MoneyTotal {
  currency: string
  /** Kanonische Schreibweise mit zwei Dezimalen, z. B. "73042.40". */
  amount: string
}

export interface CategorySummary {
  category: Category
  count: number
  totals: MoneyTotal[]
  /** Findings dieser Kategorie ohne `impact_eur`. */
  withoutImpact: number
}

export interface TierSummary {
  tier: Tier
  count: number
}

export interface DashboardSummary {
  total: number
  /** Ohne Entscheidung – die Entscheidungen der Sitzung liegen schon über den Findings. */
  open: number
  decided: number
  /** Euro-Wirkung des ganzen Laufs, je Währung. */
  totals: MoneyTotal[]
  /** Findings ohne Euro-Wirkung. Benannt statt als 0,00 € mitgezählt (Regel 4). */
  withoutImpact: number
  /** Nur Kategorien, die im Lauf vorkommen. */
  byCategory: CategorySummary[]
  /** Alle vier Stufen in fester Reihenfolge, auch mit 0. */
  byTier: TierSummary[]
  /** Findings mit Euro-Wirkung, absteigend, höchstens `TOP_COUNT`. */
  top: Finding[]
}

/** Länge der Top-Liste (Spec Sprint 5, Aufgabe 6). */
export const TOP_COUNT = 10

function compareCents(a: bigint, b: bigint): number {
  if (a < b) return -1
  if (a > b) return 1
  return 0
}

function compareText(a: string, b: string): number {
  if (a < b) return -1
  if (a > b) return 1
  return 0
}

/**
 * Summiert die Euro-Wirkung je Währung. Absteigend nach Betrag, bei Gleichstand
 * nach Währungscode – mit den Beispielen ist das genau eine Zeile („73.042,40 €").
 */
function sumByCurrency(findings: readonly Finding[]): MoneyTotal[] {
  const totals = new Map<string, bigint>()
  for (const finding of findings) {
    const impact = finding.impact_eur
    if (impact == null) continue
    totals.set(impact.currency, (totals.get(impact.currency) ?? 0n) + parseCents(impact.amount))
  }
  return [...totals.entries()]
    .map(([currency, cents]) => ({ currency, amount: centsToAmount(cents) }))
    .sort((a, b) => {
      const byAmount = compareCents(parseCents(b.amount), parseCents(a.amount))
      return byAmount !== 0 ? byAmount : compareText(a.currency, b.currency)
    })
}

function amountFor(totals: readonly MoneyTotal[], currency: string): bigint {
  const total = totals.find((entry) => entry.currency === currency)
  return total == null ? 0n : parseCents(total.amount)
}

/**
 * Kategorien nach Euro-Wirkung absteigend.
 *
 * Verglichen wird Währung für Währung in der Reihenfolge des ganzen Laufs (die
 * größte zuerst): bei einer Währung ist das schlicht „nach Betrag absteigend", bei
 * mehreren bleibt es eine Reihenfolge, ohne Kurse zu erfinden. Gleichstand geht
 * nach Kategoriename, damit nichts der Zufallsreihenfolge einer `Map` überlassen ist.
 */
function compareCategories(currencyOrder: readonly string[]) {
  return (a: CategorySummary, b: CategorySummary): number => {
    for (const currency of currencyOrder) {
      const byAmount = compareCents(amountFor(b.totals, currency), amountFor(a.totals, currency))
      if (byAmount !== 0) return byAmount
    }
    return compareText(a.category, b.category)
  }
}

/**
 * Alle Zahlen des Dashboards aus einem Lauf.
 *
 * Grundlage ist der ganze Lauf, nicht die gefilterte Liste des Explorers: die
 * Kacheln beschreiben den Datenstand, nicht die gerade eingestellte Sicht.
 */
export function summarize(findings: readonly Finding[]): DashboardSummary {
  const totals = sumByCurrency(findings)
  const currencyOrder = totals.map((total) => total.currency)

  const categories = new Map<Category, Finding[]>()
  for (const finding of findings) {
    const bucket = categories.get(finding.category)
    if (bucket == null) categories.set(finding.category, [finding])
    else bucket.push(finding)
  }

  const byCategory = [...categories.entries()]
    .map(([category, group]) => ({
      category,
      count: group.length,
      totals: sumByCurrency(group),
      withoutImpact: group.filter((finding) => finding.impact_eur == null).length,
    }))
    .sort(compareCategories(currencyOrder))

  const byTier = TIERS.map((tier) => ({
    tier,
    count: findings.filter((finding) => finding.tier === tier).length,
  }))

  const withImpact = findings.filter((finding) => finding.impact_eur != null)
  const open = findings.filter(isOpen).length

  return {
    total: findings.length,
    open,
    decided: findings.length - open,
    totals,
    withoutImpact: findings.length - withImpact.length,
    byCategory,
    byTier,
    // Dieselbe Reihenfolge wie die Standardsortierung der Tabelle: Euro-Wirkung
    // absteigend, dann Schwere, zuletzt `finding_id`.
    top: sortFindings(withImpact).slice(0, TOP_COUNT),
  }
}
