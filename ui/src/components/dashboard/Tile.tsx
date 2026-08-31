import type { ReactNode } from 'react'
import { formatMoney } from '@/lib/format'
import type { MoneyTotal } from '@/lib/dashboard'
import { cn } from '@/lib/utils'

/**
 * Kachelrahmen des Dashboards: Überschrift, Inhalt, optionale Fußzeile.
 *
 * Gleiche Tonlage wie die Abschnitte der Review-Karte (docs/CONCEPT.md, Abschnitt 9):
 * ruhig und dicht, Farbe tragen nur die Badges, nicht die Flächen.
 */
export function Tile({
  title,
  children,
  footer,
  className,
}: {
  title: string
  children: ReactNode
  footer?: ReactNode
  className?: string
}) {
  return (
    <section className={cn('flex flex-col rounded-lg border p-4', className)}>
      <h2 className="text-[0.7rem] font-medium tracking-wider text-muted-foreground uppercase">
        {title}
      </h2>
      <div className="mt-2 flex-1">{children}</div>
      {footer != null && <div className="mt-3 text-xs text-muted-foreground">{footer}</div>}
    </section>
  )
}

/** Kachel mit einer großen Zahl und einer erläuternden Zeile darunter. */
export function StatTile({
  title,
  value,
  footer,
  className,
}: {
  title: string
  value: ReactNode
  footer?: ReactNode
  className?: string
}) {
  return (
    <Tile title={title} footer={footer} className={className}>
      <div className="font-mono text-3xl tabular-nums">{value}</div>
    </Tile>
  )
}

/**
 * Summen je Währung untereinander. Es wird nichts umgerechnet und nichts
 * zusammengezogen – die Währung steht immer neben dem Betrag (CLAUDE.md, Regel 2).
 */
export function MoneyTotals({
  totals,
  className,
}: {
  totals: readonly MoneyTotal[]
  className?: string
}) {
  if (totals.length === 0) {
    return <span className={cn('text-muted-foreground', className)}>–</span>
  }
  return (
    <div className={cn('flex flex-col', className)}>
      {totals.map((total) => (
        <span key={total.currency}>{formatMoney(total.amount, total.currency)}</span>
      ))}
    </div>
  )
}
