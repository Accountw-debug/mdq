import { Key } from '@/components/Key'
import { LabelValue, Section } from '@/components/review/Section'
import { formatDateOrNull, formatMoney } from '@/lib/format'
import { hasRelevance } from '@/lib/review'
import type { Finding } from '@/types/finding'

/**
 * Relevanz (Spec Sprint 5, Aufgabe 3, Punkt 7): offene Posten, 12-Monats-Volumen,
 * letzte Aktivität. Fehlt der ganze Block, erscheint er nicht.
 *
 * Die Beträge stehen in der Hauswährung des Buchungskreises und sind nicht
 * umgerechnet; gezeigt werden sie deshalb mit `relevance.currency` statt mit einem
 * festen Eurozeichen (CLAUDE.md, Regel 2).
 */
export function Relevance({ finding }: { finding: Finding }) {
  if (!hasRelevance(finding)) return null
  const relevance = finding.relevance
  if (!relevance) return null
  const money = (amount: string | null | undefined) =>
    amount == null ? null : formatMoney(amount, relevance.currency)
  const openItems = money(relevance.open_items)
  const volume = money(relevance.volume_12m)
  const lastActivity = formatDateOrNull(relevance.last_activity_on)

  return (
    <Section title="Relevanz">
      <dl className="flex flex-wrap gap-x-8 gap-y-2">
        {openItems && (
          <LabelValue label="Offene Posten">
            <Key className="tabular-nums">{openItems}</Key>
          </LabelValue>
        )}
        {volume && (
          <LabelValue label="Volumen 12 Monate">
            <Key className="tabular-nums">{volume}</Key>
          </LabelValue>
        )}
        {lastActivity && <LabelValue label="Letzte Aktivität">{lastActivity}</LabelValue>}
      </dl>
    </Section>
  )
}
