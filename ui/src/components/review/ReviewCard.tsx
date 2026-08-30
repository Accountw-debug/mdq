import { useEffect, useState } from 'react'
import { ActionTypeBadge, DamageClassBadge, SeverityBadge, TierBadge } from '@/components/Badges'
import { Key } from '@/components/Key'
import { ActionBar } from '@/components/review/ActionBar'
import { AssignDialog } from '@/components/review/AssignDialog'
import { CurrentProposed } from '@/components/review/CurrentProposed'
import { EvidencePanel } from '@/components/review/EvidencePanel'
import { Explanation } from '@/components/review/Explanation'
import { ImpactSection } from '@/components/review/ImpactSection'
import { RejectDialog } from '@/components/review/RejectDialog'
import { Relevance } from '@/components/review/Relevance'
import { Remediation } from '@/components/review/Remediation'
import { formatMoney } from '@/lib/format'
import { acceptBlockedReason, createDecision } from '@/lib/review'
import type { DecisionRecord, ReasonCode } from '@/types/decision'
import type { Finding } from '@/types/finding'

/**
 * Die Review-Karte – der Kern der Anwendung (docs/CONCEPT.md, Abschnitt 9).
 *
 * Bewusst ohne Sheet und ohne Portal: `ReviewDrawer` hängt sie in den Drawer, der
 * Rauchtest rendert sie direkt zu HTML. Die Reihenfolge der Abschnitte steht in der
 * Spec und ist die Reihenfolge, in der ein Buchhalter entscheidet: erst wer und wie
 * viel, dann Ist gegen Soll, dann die Belege, dann die Folgen, dann der Weg im SAP.
 *
 * Abschnitte ohne Inhalt geben `null` zurück und erscheinen gar nicht – ein „–"
 * würde Arbeit vortäuschen, die es nicht gibt.
 */
export function ReviewCard({
  finding,
  decision,
  reviewer,
  onDecide,
  onClearDecision,
  onLater,
  onMove,
}: {
  finding: Finding
  decision: DecisionRecord | undefined
  reviewer: string
  onDecide: (record: DecisionRecord) => void
  onClearDecision: (findingId: string) => void
  onLater: () => void
  onMove: (delta: number) => void
}) {
  const [chosenOption, setChosenOption] = useState<string | null>(null)
  const [dialog, setDialog] = useState<'reject' | 'assign' | null>(null)

  const canDecide = reviewer.trim() !== ''

  function accept() {
    if (!canDecide || acceptBlockedReason(finding, chosenOption) != null) return
    onDecide(
      createDecision({
        findingId: finding.finding_id,
        action: 'accept',
        by: reviewer,
        chosenOption,
      }),
    )
  }

  function reject(reasonCode: ReasonCode, reason: string) {
    setDialog(null)
    onDecide(
      createDecision({
        findingId: finding.finding_id,
        action: 'reject',
        by: reviewer,
        reasonCode,
        reason,
      }),
    )
  }

  function assign(assignedTo: string) {
    setDialog(null)
    onDecide(
      createDecision({
        findingId: finding.finding_id,
        action: 'assign',
        by: reviewer,
        assignedTo,
      }),
    )
  }

  // Tastatur der offenen Karte. Im Dialog gehören die Tasten dem Dialog.
  // Bewusst ohne Abhängigkeitsliste: der Zuhörer soll immer die aktuelle Wahl und
  // den aktuellen Bearbeiter sehen, und ein Fenster-Listener ist billig zu tauschen.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey || dialog != null) return
      const target = event.target as HTMLElement | null
      if (
        target != null &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable === true)
      ) {
        return
      }

      switch (event.key) {
        case 'a':
        case 'A':
          event.preventDefault()
          accept()
          break
        case 'r':
        case 'R':
          if (!canDecide) break
          event.preventDefault()
          setDialog('reject')
          break
        case 'z':
        case 'Z':
          if (!canDecide) break
          event.preventDefault()
          setDialog('assign')
          break
        case 'j':
        case 'J':
          event.preventDefault()
          onMove(1)
          break
        case 'k':
        case 'K':
          event.preventDefault()
          onMove(-1)
          break
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  })

  const impact = finding.impact_eur

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="border-b p-4 pr-12">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="font-heading text-base font-medium">
              {finding.entity.display_name ?? finding.entity.bp_key}
            </h2>
            <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
              <Key>{finding.entity.bp_key}</Key>
              {finding.entity.company_code && (
                <>
                  <span aria-hidden>·</span>
                  <span>
                    Buchungskreis <Key>{finding.entity.company_code}</Key>
                  </span>
                </>
              )}
              <span aria-hidden>·</span>
              <Key>{finding.rule_id}</Key>
              <span>v{finding.rule_version}</span>
            </div>
          </div>
          {impact && (
            <div className="shrink-0 text-right">
              <div className="font-mono text-xl tabular-nums">
                {formatMoney(impact.amount, impact.currency)}
              </div>
              <div className="text-xs text-muted-foreground">Euro-Wirkung</div>
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5 pt-2">
          <TierBadge tier={finding.tier} />
          <SeverityBadge severity={finding.severity} />
          <DamageClassBadge damageClass={finding.damage_class} />
          <ActionTypeBadge actionType={finding.action_type} />
        </div>

        {finding.title && <p className="pt-2 text-sm font-medium">{finding.title}</p>}
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <CurrentProposed
          finding={finding}
          chosenOption={chosenOption}
          onChooseOption={setChosenOption}
        />
        <EvidencePanel finding={finding} />
        <ImpactSection finding={finding} />
        <Explanation finding={finding} />
        <Remediation finding={finding} />
        <Relevance finding={finding} />
      </div>

      <footer className="border-t bg-muted/20 p-4">
        <ActionBar
          finding={finding}
          decision={decision}
          reviewer={reviewer}
          chosenOption={chosenOption}
          onAccept={accept}
          onOpenReject={() => setDialog('reject')}
          onOpenAssign={() => setDialog('assign')}
          onLater={onLater}
          onClearDecision={() => onClearDecision(finding.finding_id)}
        />
      </footer>

      <RejectDialog
        open={dialog === 'reject'}
        onOpenChange={(open) => setDialog(open ? 'reject' : null)}
        onConfirm={reject}
      />
      <AssignDialog
        open={dialog === 'assign'}
        onOpenChange={(open) => setDialog(open ? 'assign' : null)}
        onConfirm={assign}
      />
    </div>
  )
}
