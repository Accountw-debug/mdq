import { Badge } from '@/components/ui/badge'
import { Key } from '@/components/Key'
import { LabelValue, Section } from '@/components/review/Section'
import type { Finding } from '@/types/finding'

/**
 * „Wie beheben" (Spec Sprint 5, Aufgabe 3, Punkt 6): Transaktion, Pfad, Feld und
 * die Schritte in der Reihenfolge, in der sie im SAP zu tun sind.
 *
 * Transaktion und Feld in Monospace – sie werden abgetippt oder kopiert.
 */
export function Remediation({ finding }: { finding: Finding }) {
  const { remediation } = finding
  const steps = remediation.steps ?? []

  return (
    <Section title="Wie beheben">
      <dl className="flex flex-wrap gap-x-8 gap-y-2">
        <LabelValue label="Transaktion">
          <Key className="text-[0.95em] font-medium">{remediation.sap_transaction}</Key>
        </LabelValue>
        {remediation.path && <LabelValue label="Pfad">{remediation.path}</LabelValue>}
        {remediation.field && (
          <LabelValue label="Feld">
            <Key className="text-[0.95em]">{remediation.field}</Key>
          </LabelValue>
        )}
      </dl>

      {steps.length > 0 && (
        <ol className="mt-3 flex list-decimal flex-col gap-1 pl-5 marker:text-muted-foreground marker:tabular-nums">
          {steps.map((step, index) => (
            <li key={`${index}-${step}`}>{step}</li>
          ))}
        </ol>
      )}

      {remediation.mass_change_eligible && (
        <Badge variant="outline" className="mt-3 font-normal">
          massenänderungsfähig
        </Badge>
      )}
    </Section>
  )
}
