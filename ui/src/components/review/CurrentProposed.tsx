import { Key } from '@/components/Key'
import { Section } from '@/components/review/Section'
import { cn } from '@/lib/utils'
import type { Finding, ProposedOption } from '@/types/finding'

/**
 * Ist | Soll nebeneinander (Spec Sprint 5, Aufgabe 3, Punkt 2).
 *
 * Links steht, was im Quellsystem steht – Tabelle und Feld in Monospace, damit der
 * Weg nach SAP klar ist. Rechts steht der Vorschlag mit seiner Quellenlage. Gibt es
 * keinen Vorschlag, steht dort der Hinweis, dass entschieden werden muss – nie ein
 * erfundener Wert.
 */
export function CurrentProposed({
  finding,
  chosenOption,
  onChooseOption,
}: {
  finding: Finding
  chosenOption: string | null
  onChooseOption: (label: string | null) => void
}) {
  const { current, proposed } = finding
  const options = proposed?.options ?? []
  const hasProposedValue = proposed?.value != null && proposed.value !== ''

  return (
    <Section title="Ist und Soll">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg border bg-muted/30 p-3">
          <div className="text-xs font-medium">Ist</div>
          <div className="mt-1">
            <Key className="text-muted-foreground">
              {current.source_table}.{current.source_field}
            </Key>
          </div>
          <p className="mt-2 break-words">
            {current.value == null || current.value === '' ? (
              <span className="text-muted-foreground italic">leer</span>
            ) : (
              <Key className="text-[0.95em]">{current.value}</Key>
            )}
          </p>
          {current.display && (
            <p className="mt-1 text-xs text-muted-foreground">{current.display}</p>
          )}
        </div>

        <div className="rounded-lg border p-3">
          <div className="text-xs font-medium">Soll</div>
          {hasProposedValue ? (
            <p className="mt-2 break-words">
              <Key className="text-[0.95em]">{proposed?.value}</Key>
            </p>
          ) : (
            <p className="mt-2 text-muted-foreground">
              Kein Soll ermittelbar – Entscheidung/Prüfung
            </p>
          )}
          {proposed?.display && (
            <p className={cn('text-xs text-muted-foreground', hasProposedValue ? 'mt-1' : 'mt-2')}>
              {proposed.display}
            </p>
          )}
          {proposed?.source_summary && (
            <p className="mt-3 border-t pt-2 text-xs">
              <span className="text-muted-foreground">Quellenlage: </span>
              {proposed.source_summary}
            </p>
          )}
        </div>
      </div>

      {options.length > 0 && (
        <Options options={options} chosen={chosenOption} onChoose={onChooseOption} />
      )}
    </Section>
  )
}

/**
 * Optionen einer Entscheidung als wählbare Karten. Die Wahl ist keine Spielerei:
 * sie steht anschließend als Grund im Entscheidungssatz, damit im Export nachlesbar
 * bleibt, wofür sich der Bearbeiter entschieden hat.
 */
function Options({
  options,
  chosen,
  onChoose,
}: {
  options: readonly ProposedOption[]
  chosen: string | null
  onChoose: (label: string | null) => void
}) {
  return (
    <div className="mt-3">
      <div className="text-xs text-muted-foreground">Optionen – eine wählen, dann übernehmen</div>
      <div className="mt-1.5 grid gap-2 sm:grid-cols-2">
        {options.map((option) => {
          const active = option.label === chosen
          return (
            <button
              key={option.label}
              type="button"
              aria-pressed={active}
              onClick={() => onChoose(active ? null : option.label)}
              className={cn(
                'rounded-lg border p-3 text-left outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50',
                active
                  ? 'border-ring bg-muted/70'
                  : 'hover:bg-muted/40',
              )}
            >
              <div className="text-sm font-medium">{option.label}</div>
              <div className="mt-1 text-xs text-muted-foreground">{option.consequence}</div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
