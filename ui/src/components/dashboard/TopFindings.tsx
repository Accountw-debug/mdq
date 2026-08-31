import { SeverityBadge, TierBadge } from '@/components/Badges'
import { Key } from '@/components/Key'
import { Tile } from '@/components/dashboard/Tile'
import { TOP_COUNT } from '@/lib/dashboard'
import { formatMoney } from '@/lib/format'
import type { Finding } from '@/types/finding'

/**
 * Top-Liste nach Euro-Wirkung (Spec Sprint 5, Aufgabe 6), klickbar bis zur Karte.
 *
 * Gelistet sind nur Findings mit `impact_eur`. Wer keine Euro-Wirkung trägt, stünde
 * sonst mit „0,00 €" in einer Rangliste, in die er nicht gehört – die Anzahl steht
 * stattdessen als Satz darunter (Freigabe Victor, 2026-08-30; CLAUDE.md, Regel 4).
 *
 * Jede Zeile ist ein Knopf, damit die Liste auch mit der Tastatur erreichbar ist.
 */
export function TopFindings({
  findings,
  withoutImpact,
  onOpenFinding,
}: {
  findings: readonly Finding[]
  withoutImpact: number
  onOpenFinding: (finding: Finding) => void
}) {
  return (
    <Tile
      title={`Top ${TOP_COUNT} nach Euro-Wirkung`}
      footer={
        withoutImpact === 0 ? undefined : (
          <>
            {withoutImpact === 1
              ? '1 Finding ohne Euro-Wirkung'
              : `${withoutImpact} Findings ohne Euro-Wirkung`}{' '}
            – nicht gelistet, weil die Engine dafür keinen Betrag ausweist.
          </>
        )
      }
    >
      {findings.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Kein Finding dieses Laufs weist eine Euro-Wirkung aus.
        </p>
      ) : (
        <ol className="flex flex-col">
          {findings.map((finding, index) => (
            <TopRow
              key={finding.finding_id}
              finding={finding}
              rank={index + 1}
              onOpenFinding={onOpenFinding}
            />
          ))}
        </ol>
      )}
    </Tile>
  )
}

function TopRow({
  finding,
  rank,
  onOpenFinding,
}: {
  finding: Finding
  rank: number
  onOpenFinding: (finding: Finding) => void
}) {
  const impact = finding.impact_eur
  // Die Liste enthält nur Findings mit Betrag; ohne einen gehört die Zeile nicht her.
  if (impact == null) return null

  return (
    <li>
      <button
        type="button"
        onClick={() => onOpenFinding(finding)}
        className="flex w-full items-center gap-3 rounded-md px-2 py-2 text-left outline-none transition-colors hover:bg-muted/60 focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <span className="w-5 shrink-0 text-right font-mono text-xs text-muted-foreground tabular-nums">
          {rank}
        </span>
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="flex items-baseline gap-2">
            <Key>{finding.entity.bp_key}</Key>
            <span className="truncate text-sm">{finding.entity.display_name ?? '—'}</span>
          </span>
          <span className="truncate text-xs text-muted-foreground">
            {finding.title}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-1.5">
          <TierBadge tier={finding.tier} />
          <SeverityBadge severity={finding.severity} />
        </span>
        <span className="w-32 shrink-0 text-right font-mono text-sm tabular-nums">
          {formatMoney(impact.amount, impact.currency)}
        </span>
      </button>
    </li>
  )
}
