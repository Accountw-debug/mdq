import { CheckIcon, XIcon } from 'lucide-react'
import { Key } from '@/components/Key'
import { Section } from '@/components/review/Section'
import { formatDateOrNull } from '@/lib/format'
import { SOURCE_TYPE_LABELS } from '@/lib/labels'
import { sortEvidence } from '@/lib/review'
import { cn } from '@/lib/utils'
import type { Evidence, Finding } from '@/types/finding'

/**
 * Evidenz-Panel (Spec Sprint 5, Aufgabe 3, Punkt 3): je Eintrag eine Karte mit
 * Quellentyp, Referenz, Wert, Datum, Übereinstimmung und Notiz.
 *
 * Widersprüche stehen oben. Wer eine Zahlung stoppt, muss zuerst sehen, was gegen
 * den Vorschlag spricht – nicht drei Bestätigungen weiter unten.
 */
export function EvidencePanel({ finding }: { finding: Finding }) {
  const evidence = finding.evidence ?? []
  if (evidence.length === 0) return null

  const sorted = sortEvidence(evidence)
  const contradictions = sorted.filter((entry) => !entry.agrees).length

  return (
    <Section title={`Evidenz (${sorted.length})`}>
      {contradictions > 0 && (
        <p className="mb-2 text-xs text-muted-foreground">
          {contradictions === 1 ? 'Ein Eintrag widerspricht' : `${contradictions} Einträge widersprechen`} dem
          Soll und steht zuerst.
        </p>
      )}
      <ul className="flex flex-col gap-2">
        {sorted.map((entry, index) => (
          <li key={`${entry.source_type}-${entry.reference}-${index}`}>
            <EvidenceCard entry={entry} />
          </li>
        ))}
      </ul>
    </Section>
  )
}

function EvidenceCard({ entry }: { entry: Evidence }) {
  const observedAt = formatDateOrNull(entry.observed_at)

  return (
    <div
      className={cn(
        'rounded-lg border p-3',
        entry.agrees ? 'bg-muted/20' : 'border-destructive/30 bg-destructive/5',
      )}
    >
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <Agreement agrees={entry.agrees} />
        <span className="text-sm font-medium">{SOURCE_TYPE_LABELS[entry.source_type]}</span>
        <Key className="text-muted-foreground">{entry.reference}</Key>
        {observedAt && <span className="ml-auto text-xs text-muted-foreground">{observedAt}</span>}
      </div>
      {entry.value && (
        <p className="mt-1.5 break-words">
          <Key className="text-[0.95em]">{entry.value}</Key>
        </p>
      )}
      {entry.note && <p className="mt-1 text-xs text-muted-foreground">{entry.note}</p>}
    </div>
  )
}

function Agreement({ agrees }: { agrees: boolean }) {
  const Icon = agrees ? CheckIcon : XIcon
  return (
    <span
      className={cn(
        'inline-flex items-center',
        agrees ? 'text-emerald-600 dark:text-emerald-400' : 'text-destructive',
      )}
      title={agrees ? 'stützt das Soll' : 'widerspricht dem Soll'}
    >
      <Icon className="size-4" aria-hidden />
      <span className="sr-only">{agrees ? 'stützt das Soll' : 'widerspricht dem Soll'}</span>
    </span>
  )
}
