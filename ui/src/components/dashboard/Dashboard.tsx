import { useMemo } from 'react'
import { CategoryImpact } from '@/components/dashboard/CategoryImpact'
import { MoneyTotals, StatTile, Tile } from '@/components/dashboard/Tile'
import { TierDistribution } from '@/components/dashboard/TierDistribution'
import { TopFindings } from '@/components/dashboard/TopFindings'
import { summarize } from '@/lib/dashboard'
import type { Finding } from '@/types/finding'

/**
 * Dashboard: Kacheln, Verteilung nach Stufe und Top-Liste (Spec Sprint 5, Aufgabe 6).
 *
 * Die Zahlen beschreiben den ganzen Lauf, nicht die im Explorer eingestellte Sicht –
 * Filter gehören zur Suche, nicht zur Lage. Die Entscheidungen der Sitzung liegen
 * dagegen schon über den Findings: wer entscheidet, sieht „davon offen" fallen,
 * auch ohne Export (Freigabe Victor, 2026-08-30).
 *
 * Der Rahmen der App ist fensterhoch und scrollt nicht; diese Ansicht kann lang
 * werden und bringt deshalb ihren eigenen Scrollbereich mit.
 */
export function Dashboard({
  findings,
  onOpenFinding,
}: {
  findings: readonly Finding[]
  onOpenFinding: (finding: Finding) => void
}) {
  const summary = useMemo(() => summarize(findings), [findings])

  if (summary.total === 0) {
    return (
      <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
        Dieser Lauf enthält keine Findings. Es gibt nichts zu zeigen – und nichts, was
        das Dashboard daraus schätzen würde.
      </p>
    )
  }

  return (
    <div className="@container min-h-0 flex-1 overflow-y-auto">
      <div className="flex flex-col gap-4 pb-2">
        <div className="grid gap-4 @min-[56rem]:grid-cols-3">
          <StatTile
            title="Findings gesamt"
            value={summary.total}
            footer={
              <>
                davon <span className="font-mono tabular-nums">{summary.open}</span> offen ·{' '}
                <span className="font-mono tabular-nums">{summary.decided}</span> entschieden
              </>
            }
          />
          <Tile
            title="Euro-Wirkung gesamt"
            footer={
              summary.withoutImpact === 0
                ? 'Jedes Finding weist einen Betrag aus.'
                : `${summary.withoutImpact} von ${summary.total} Findings ohne Euro-Wirkung`
            }
          >
            <MoneyTotals totals={summary.totals} className="font-mono text-3xl tabular-nums" />
          </Tile>
          {/*
            Platzhalter, keine Zahl: der Score wird in Sprint 4 berechnet. Eine
            erfundene Kennzahl wäre die eine Zahl auf diesem Bildschirm, die niemand
            nachrechnen kann (Spec Sprint 5, Aufgabe 6).
          */}
          <Tile title="Score" className="border-dashed" footer="Kennzahl je Mandant.">
            <div className="text-lg text-muted-foreground">ab Sprint 4</div>
          </Tile>
        </div>

        <div className="grid gap-4 @min-[56rem]:grid-cols-2">
          <CategoryImpact categories={summary.byCategory} />
          <TierDistribution tiers={summary.byTier} total={summary.total} />
        </div>

        <TopFindings
          findings={summary.top}
          withoutImpact={summary.withoutImpact}
          onOpenFinding={onOpenFinding}
        />
      </div>
    </div>
  )
}
