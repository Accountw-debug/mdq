import { Section } from '@/components/review/Section'
import { formatMoney } from '@/lib/format'
import type { Finding } from '@/types/finding'

/**
 * Euro-Wirkung mit offengelegter Rechnung (Spec Sprint 5, Aufgabe 3, Punkt 4).
 *
 * Die `formula` steht wörtlich da, wie die Engine sie geschrieben hat: eine Zahl
 * ohne nachvollziehbare Herkunft ist im Gespräch mit dem Kunden wertlos.
 */
export function ImpactSection({ finding }: { finding: Finding }) {
  const impact = finding.impact_eur
  if (!impact) return null

  return (
    <Section title="Euro-Wirkung">
      <div className="font-mono text-2xl tabular-nums">
        {formatMoney(impact.amount, impact.currency)}
      </div>
      <p className="mt-2 rounded-lg border bg-muted/30 px-3 py-2 font-mono text-xs break-words">
        {impact.formula}
      </p>
      {impact.netted_against && (
        <p className="mt-1.5 text-xs">
          <span className="text-muted-foreground">Verrechnet gegen: </span>
          {impact.netted_against}
        </p>
      )}
    </Section>
  )
}
