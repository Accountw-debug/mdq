import { Tile } from '@/components/dashboard/Tile'
import { TierBadge } from '@/components/Badges'
import type { TierSummary } from '@/lib/dashboard'
import { TIER_LABELS } from '@/lib/labels'

/**
 * Verteilung nach Stufe (Spec Sprint 5, Aufgabe 6).
 *
 * Alle vier Stufen stehen da, auch mit 0 – dass eine Stufe fehlt, ist die Aussage:
 * ohne Stufe A gibt es im Lauf nichts massenänderungsfähiges. Der Anteil steht als
 * Bruch („3 von 6") statt als gerundete Prozentzahl; der Balken ist nur das Bild
 * dazu, keine zweite Zahl.
 */
export function TierDistribution({ tiers, total }: { tiers: readonly TierSummary[]; total: number }) {
  return (
    <Tile title="Verteilung nach Stufe">
      <dl className="flex flex-col gap-2">
        {tiers.map((entry) => (
          <div key={entry.tier} className="flex items-center gap-3">
            <dt className="flex w-40 shrink-0 items-center gap-2">
              <TierBadge tier={entry.tier} />
              <span className="truncate text-sm">{TIER_LABELS[entry.tier]}</span>
            </dt>
            <dd className="flex min-w-0 flex-1 items-center gap-3">
              <div
                aria-hidden
                className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-muted"
              >
                <div
                  className="h-full rounded-full bg-foreground/30"
                  style={{ width: barWidth(entry.count, total) }}
                />
              </div>
              <span className="shrink-0 font-mono text-xs text-muted-foreground tabular-nums">
                {entry.count} von {total}
              </span>
            </dd>
          </div>
        ))}
      </dl>
    </Tile>
  )
}

/** Breite des Balkens – Bild, kein Wert; deshalb darf hier gerundet werden. */
function barWidth(count: number, total: number): string {
  if (total === 0 || count === 0) return '0%'
  return `${(count / total) * 100}%`
}
