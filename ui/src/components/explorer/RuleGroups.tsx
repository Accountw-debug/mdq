import { CheckIcon, ShieldAlertIcon } from 'lucide-react'
import { TierBadge } from '@/components/Badges'
import { Key } from '@/components/Key'
import { MoneyTotals } from '@/components/dashboard/Tile'
import { Button } from '@/components/ui/button'
import { formatDateTime } from '@/lib/format'
import { SAMPLE_SIZE, type RuleGroup } from '@/lib/sampling'
import type { SamplesState } from '@/state/samples'

/**
 * Regelgruppen im Tab Massenänderung (Spec Sprint 5, Aufgabe 7).
 *
 * Eine Massenänderung wird nicht Finding für Finding entschieden – 240-mal
 * dieselbe Regel zu bestätigen prüft nichts, es ermüdet nur. Geprüft wird eine
 * Stichprobe, freigegeben wird die Gruppe.
 *
 * Die Gruppen zählen den ganzen Tab, nicht die gefilterte Tabelle: ein Filter ist
 * eine Sicht, kein anderer Befund.
 */

const MISSING_REVIEWER = 'Erst oben im Datenstand-Banner den Bearbeiter eintragen'
const NOTHING_OPEN = 'Keine offenen Findings in dieser Gruppe, die eine Freigabe treffen könnte'

export function RuleGroups({
  groups,
  samples,
  reviewer,
  onStartSample,
}: {
  groups: readonly RuleGroup[]
  samples: SamplesState
  reviewer: string
  onStartSample: (group: RuleGroup) => void
}) {
  if (groups.length === 0) {
    return (
      <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
        Kein Finding vom Aktionstyp Massenänderung in diesem Lauf – und damit keine Gruppe,
        für die sich eine Stichprobe ziehen ließe. Massenänderung setzt Stufe A voraus; die
        Beispiel-Findings enthalten keine.
      </p>
    )
  }

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-[0.7rem] font-medium tracking-wider text-muted-foreground uppercase">
        Regelgruppen
      </h2>
      <ul className="flex flex-col gap-2">
        {groups.map((group) => (
          <GroupRow
            key={group.rule_id}
            group={group}
            review={samples[group.rule_id]}
            reviewer={reviewer}
            onStartSample={() => onStartSample(group)}
          />
        ))}
      </ul>
    </section>
  )
}

function GroupRow({
  group,
  review,
  reviewer,
  onStartSample,
}: {
  group: RuleGroup
  review: SamplesState[string] | undefined
  reviewer: string
  onStartSample: () => void
}) {
  const sampleSize = Math.min(SAMPLE_SIZE, group.releasable)
  // Reihenfolge der Gründe: ein Ausgang steht fest, dann fehlt der Bearbeiter,
  // dann gibt es nichts mehr freizugeben.
  const blocked =
    review != null
      ? review.outcome === 'released'
        ? 'Diese Gruppe ist bereits freigegeben'
        : 'Die Gruppenfreigabe ist für diesen Lauf gesperrt'
      : reviewer.trim() === ''
        ? MISSING_REVIEWER
        : group.releasable === 0
          ? NOTHING_OPEN
          : null

  return (
    <li className="rounded-lg border p-3">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
            <TierBadge tier={group.tier} />
            <span className="whitespace-nowrap">
              <Key>{group.rule_id}</Key>{' '}
              <span className="text-xs text-muted-foreground">v{group.rule_version}</span>
            </span>
            <span className="truncate">{group.title}</span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            <span className="font-mono tabular-nums">{group.total}</span> Findings ·{' '}
            <span className="font-mono tabular-nums">{group.open}</span> offen
            {group.bankData > 0 && (
              <>
                {' · '}
                <span className="font-mono tabular-nums">{group.bankData}</span> Schadensklasse 1,
                nie über die Gruppe entschieden
              </>
            )}
            {group.mixedTier && ' · gemischte Stufen'}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <MoneyTotals
            totals={group.totals}
            className="text-right font-mono text-sm tabular-nums"
          />
          <Button
            variant="outline"
            size="sm"
            disabled={blocked != null}
            title={blocked ?? undefined}
            onClick={onStartSample}
          >
            Stichprobe prüfen
            <span className="ml-1 font-mono text-xs tabular-nums">
              ({sampleSize} von {group.releasable})
            </span>
          </Button>
        </div>
      </div>

      {review && <Outcome review={review} />}
    </li>
  )
}

/**
 * Der Ausgang der Stichprobe – er bleibt stehen, auch nach einem Export und dem
 * Import am nächsten Tag. Die Sperre ist endgültig für diesen Lauf; sie zu
 * verschweigen hieße, sie nach dem nächsten Klick zu vergessen.
 */
function Outcome({ review }: { review: SamplesState[string] }) {
  if (review.outcome === 'released') {
    return (
      <p className="mt-2 flex items-start gap-2 border-t pt-2 text-xs text-muted-foreground">
        <CheckIcon className="mt-px size-3.5 shrink-0" />
        <span>
          Freigegeben nach Stichprobe:{' '}
          <span className="font-mono tabular-nums">{review.sampled_finding_ids.length}</span> geprüft,{' '}
          <span className="font-mono tabular-nums">{review.applied_finding_ids.length}</span>{' '}
          Findings übernommen – {review.by}, {formatDateTime(review.at)}.
        </span>
      </p>
    )
  }
  return (
    <p className="mt-2 flex items-start gap-2 border-t border-destructive/30 pt-2 text-xs text-destructive">
      <ShieldAlertIcon className="mt-px size-3.5 shrink-0" />
      <span>
        Gruppenfreigabe gesperrt: In der Stichprobe wurde{' '}
        {review.blocked_by_finding_id && <Key>{review.blocked_by_finding_id}</Key>} abgelehnt. Für
        diesen Lauf bleibt es dabei; die übrigen Findings der Gruppe sind weiter einzeln
        entscheidbar.
      </span>
    </p>
  )
}
