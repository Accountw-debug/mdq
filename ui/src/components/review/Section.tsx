import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

/**
 * Abschnittsrahmen der Review-Karte: Überschrift, Inhalt, Trennlinie.
 *
 * Leere Abschnitte gehören nicht auf die Karte – nicht als „–", sondern gar nicht
 * (Spec Sprint 5, Aufgabe 3). Deshalb gibt jede Abschnittskomponente `null` zurück,
 * wenn ihre Felder fehlen; dieser Rahmen wird dann nie gerendert.
 */
export function Section({
  title,
  children,
  className,
}: {
  title: string
  children: ReactNode
  className?: string
}) {
  return (
    <section className={cn('border-b px-4 py-4 last:border-b-0', className)}>
      <h3 className="text-[0.7rem] font-medium tracking-wider text-muted-foreground uppercase">
        {title}
      </h3>
      <div className="mt-2">{children}</div>
    </section>
  )
}

/** Beschriftung über Wert – für kurze Angaben wie Relevanz oder Beleg-Feld. */
export function LabelValue({
  label,
  children,
  className,
}: {
  label: string
  children: ReactNode
  className?: string
}) {
  return (
    <div className={className}>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5">{children}</dd>
    </div>
  )
}
