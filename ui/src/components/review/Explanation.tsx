import { AlertTriangleIcon } from 'lucide-react'
import { Section } from '@/components/review/Section'
import { cn } from '@/lib/utils'
import type { Finding } from '@/types/finding'

/**
 * „Warum" und „Wenn falsch" (Spec Sprint 5, Aufgabe 3, Punkt 5).
 *
 * Bei Schadensklasse 1 steht „Wenn falsch" als Warnung: dort kostet eine falsche
 * Korrektur Geld, und genau das muss vor dem Klick zu sehen sein (CLAUDE.md, Regel 11).
 */
export function Explanation({ finding }: { finding: Finding }) {
  const warn = finding.damage_class === 1

  return (
    <>
      <Section title="Warum">
        <p className="whitespace-pre-line">{finding.why}</p>
      </Section>
      <Section title="Wenn falsch">
        <p
          className={cn(
            'whitespace-pre-line',
            warn &&
              'flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-destructive',
          )}
        >
          {warn && <AlertTriangleIcon className="mt-0.5 size-4 shrink-0" aria-hidden />}
          <span>{finding.if_wrong}</span>
        </p>
      </Section>
    </>
  )
}
