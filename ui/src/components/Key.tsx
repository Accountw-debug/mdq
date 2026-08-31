import { cn } from '@/lib/utils'

/**
 * Monospace-Darstellung für Schlüssel, Belegnummern, Tabellen-/Feldnamen und
 * SAP-Transaktionen (docs/CONCEPT.md, Abschnitt 9).
 *
 * Führende Nullen bleiben sichtbar; `select-all` macht das Kopieren nach SAP
 * zu einem Klick. Formatierung von Beträgen läuft über `@/lib/format`, nicht hier.
 */
export function Key({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <span className={cn('font-mono text-[0.9em] tracking-tight select-all', className)}>
      {children}
    </span>
  )
}
