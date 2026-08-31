import { MoneyTotals, Tile } from '@/components/dashboard/Tile'
import type { CategorySummary } from '@/lib/dashboard'
import { CATEGORY_LABELS } from '@/lib/labels'

/**
 * Euro-Wirkung je Kategorie (Spec Sprint 5, Aufgabe 6).
 *
 * Aufgeführt sind nur Kategorien, die im Lauf vorkommen. Eine Kategorie ohne
 * Euro-Wirkung – etwa Dubletten – bekommt keine 0,00 €, sondern den Vermerk, dass
 * keine ausgewiesen ist; die Null wäre eine Aussage über den Mandanten, die keine
 * Regel trifft. Trägt nur ein Teil der Findings einen Betrag, steht auch das da
 * (CLAUDE.md, Regel 4).
 */
export function CategoryImpact({ categories }: { categories: readonly CategorySummary[] }) {
  return (
    <Tile title="Euro-Wirkung je Kategorie">
      <dl className="flex flex-col gap-2">
        {categories.map((entry) => (
          <div key={entry.category} className="flex items-baseline justify-between gap-4">
            <dt className="min-w-0">
              <span className="text-sm">{CATEGORY_LABELS[entry.category]}</span>
              <span className="ml-1.5 font-mono text-xs text-muted-foreground tabular-nums">
                {entry.count}
              </span>
              {entry.totals.length > 0 && entry.withoutImpact > 0 && (
                <span className="ml-1.5 text-xs text-muted-foreground">
                  ({entry.withoutImpact} ohne Betrag)
                </span>
              )}
            </dt>
            <dd className="shrink-0 text-right">
              {entry.totals.length === 0 ? (
                <span className="text-xs text-muted-foreground">keine Euro-Wirkung</span>
              ) : (
                <MoneyTotals
                  totals={entry.totals}
                  className="items-end font-mono text-sm tabular-nums"
                />
              )}
            </dd>
          </div>
        ))}
      </dl>
    </Tile>
  )
}
