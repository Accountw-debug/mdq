import { Tile } from '@/components/dashboard/Tile'
import { TierBadge } from '@/components/Badges'
import type { TierSummary } from '@/lib/dashboard'
import { TIER_LABELS } from '@/lib/labels'

/**
 * Verteilung nach Stufe (Spec Sprint 5, Aufgabe 6).
 *
 * Alle vier Stufen stehen da, auch mit 0 – dass eine Stufe fehlt, ist die Aussage:
 * ohne Stufe A gibt es im Lauf nichts massenänderungsfähiges. Der Anteil steht als
 * Bruch („3 von 6") statt als gerundete Prozentzahl.
 */
export function TierDistribution({ tiers, total }: { tiers: readonly TierSummary[]; total: number }) {
  return (
    <Tile title="Verteilung nach Stufe">
      <dl className="flex flex-col gap-2">
        {tiers.map((entry) => (
          <div key={entry.tier} className="flex items-center gap-3">
            <dt className="flex min-w-0 flex-1 items-center gap-2">
              <TierBadge tier={entry.tier} />
              <span className="truncate text-sm">{TIER_LABELS[entry.tier]}</span>
            </dt>
            <dd className="shrink-0 font-mono text-xs text-muted-foreground tabular-nums">
              {entry.count} von {total}
            </dd>
          </div>
        ))}
      </dl>
    </Tile>
  )
}
