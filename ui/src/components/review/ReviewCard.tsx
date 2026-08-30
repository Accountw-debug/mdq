import { useEffect, useState } from 'react'
import { ActionTypeBadge, DamageClassBadge, SeverityBadge, TierBadge } from '@/components/Badges'
import { Key } from '@/components/Key'
import { ActionBar } from '@/components/review/ActionBar'
import { AssignDialog } from '@/components/review/AssignDialog'
import { CurrentProposed } from '@/components/review/CurrentProposed'
import { DocumentPairSection } from '@/components/review/DocumentPair'
import { DuplicateCompare } from '@/components/review/DuplicateCompare'
import { EvidencePanel } from '@/components/review/EvidencePanel'
import { Explanation } from '@/components/review/Explanation'
import { ImpactSection } from '@/components/review/ImpactSection'
import { RejectDialog } from '@/components/review/RejectDialog'
import { Relevance } from '@/components/review/Relevance'
import { Remediation } from '@/components/review/Remediation'
import { buildDocumentPair } from '@/lib/documents'
import { buildDuplicateComparison } from '@/lib/duplicate'
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
/** Stand des laufenden Stichproben-Durchgangs (Spec Sprint 5, Aufgabe 7). */
export interface SampleInfo {
  ruleId: string
  position: number
  size: number
}

export function ReviewCard({
  finding,
  decision,
  reviewer,
  sample,
  onDecide,
  onClearDecision,
  onLater,
  onMove,
}: {
  finding: Finding
  decision: DecisionRecord | undefined
  reviewer: string
  sample?: SampleInfo | null
  onDecide: (record: DecisionRecord) => void
  onClearDecision: (findingId: string) => void
  onLater: () => void
  onMove: (delta: number) => void
}) {
  const [chosenOption, setChosenOption] = useState<string | null>(null)
  const [dialog, setDialog] = useState<'reject' | 'assign' | null>(null)

  // Entschieden ist entschieden: die Tastatur darf die Sperre der Knöpfe nicht umgehen.
  const decided = decision != null
  const canDecide = reviewer.trim() !== '' && !decided

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
          if (!canDecide) break
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
  // Bei Dubletten tritt der Vergleich an die Stelle von Ist|Soll (Spec, Aufgabe 4).
  // Tragen die Daten ihn nicht, bleibt es beim gewohnten Abschnitt – eine halbe
  // Tabelle wäre schlechter als gar keine.
  const comparison =
    finding.category === 'duplicate' ? buildDuplicateComparison(finding) : null
  // Bei Geldabfluss mit Belegpaar steht die Belegansicht vor Ist|Soll (Spec, Aufgabe 5):
  // erst welche zwei Belege, dann welches Feld. Ohne Belege bleibt die Karte, wie sie ist.
  const documentPair = buildDocumentPair(finding)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="border-b p-4 pr-12">
        {/* Die Stichprobe zuerst: sie erklärt, warum diese Karte gerade offen ist
            und wie viele noch kommen (Spec Sprint 5, Aufgabe 7). */}
        {sample && (
          <p className="pb-2 text-xs text-muted-foreground">
            Stichprobe Regel <Key>{sample.ruleId}</Key> ·{' '}
            <span className="font-mono tabular-nums">
              {sample.position} von {sample.size}
            </span>
          </p>
        )}
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
              {/* Regel und Version bleiben zusammen – „v1.0" allein in einer Zeile
                  ist keine Angabe (Beobachtung Victor, 3b). */}
              <span className="whitespace-nowrap">
                <Key>{finding.rule_id}</Key> v{finding.rule_version}
              </span>
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

      {/*
        `@container`: Ob Ist und Soll nebeneinander passen, hängt an der Breite der Karte,
        nicht an der des Browserfensters. Die Abschnitte messen deshalb diesen Kasten.
      */}
      <div className="@container min-h-0 flex-1 overflow-y-auto">
        {documentPair && <DocumentPairSection pair={documentPair} />}
        {comparison ? (
          <DuplicateCompare finding={finding} comparison={comparison} />
        ) : (
          <CurrentProposed
            finding={finding}
            chosenOption={chosenOption}
            onChooseOption={setChosenOption}
            omitSourceSummary={documentPair != null}
          />
        )}
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
