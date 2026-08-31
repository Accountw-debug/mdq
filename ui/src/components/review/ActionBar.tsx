import type { ReactNode } from 'react'
import { CheckIcon, ClockIcon, RotateCcwIcon, UserPlusIcon, XIcon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { formatDateTime } from '@/lib/format'
import { DECISION_ACTION_LABELS } from '@/lib/labels'
import { acceptBlockedReason, decisionStatusLabel } from '@/lib/review'
import type { DecisionRecord } from '@/types/decision'
import type { Finding } from '@/types/finding'

/**
 * Aktionen der Review-Karte (Spec Sprint 5, Aufgabe 3, Punkt 8).
 *
 * „Übernehmen" ist bei Schadensklasse 1 gesperrt – Bankdaten nie im Alleingang
 * (CLAUDE.md, Regel 11). Der Grund steht im Tooltip, nicht im Kleingedruckten.
 * Ohne Bearbeiternamen ist keine Entscheidung möglich: `decision.by` ist Pflicht.
 *
 * Ist entschieden, sind alle drei Entscheidungen gesperrt – ein zweiter Klick würde die
 * erste Entscheidung stillschweigend überschreiben. Der Weg zurück heißt „Zurücknehmen".
 * „Später" bleibt frei: es schreibt nichts, es springt nur weiter.
 */

const MISSING_REVIEWER = 'Erst oben im Datenstand-Banner den Bearbeiter eintragen'
const ALREADY_DECIDED = 'Bereits entschieden – erst zurücknehmen'

export function ActionBar({
  finding,
  decision,
  reviewer,
  chosenOption,
  onAccept,
  onOpenReject,
  onOpenAssign,
  onLater,
  onClearDecision,
}: {
  finding: Finding
  decision: DecisionRecord | undefined
  reviewer: string
  chosenOption: string | null
  onAccept: () => void
  onOpenReject: () => void
  onOpenAssign: () => void
  onLater: () => void
  onClearDecision: () => void
}) {
  const noReviewer = reviewer.trim() === ''
  const decided = decision != null
  const acceptBlocked = acceptBlockedReason(finding, chosenOption)
  // Reihenfolge der Gründe: entschieden schlägt alles, dann der fehlende Bearbeiter.
  const blocked = decided ? ALREADY_DECIDED : noReviewer ? MISSING_REVIEWER : null

  return (
    <div className="flex flex-col gap-2">
      {decision && (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border bg-muted/40 px-3 py-2 text-xs">
          <span className="font-medium">{DECISION_ACTION_LABELS[decision.action]}</span>
          <span aria-hidden>·</span>
          <span>{decisionStatusLabel(decision)}</span>
          <span aria-hidden>·</span>
          <span className="text-muted-foreground">
            {decision.by}, {formatDateTime(decision.at)}
          </span>
          <span className="basis-full text-muted-foreground">{decision.reason}</span>
          <Button variant="ghost" size="xs" className="ml-auto" onClick={onClearDecision}>
            <RotateCcwIcon data-icon="inline-start" />
            Zurücknehmen
          </Button>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Guarded reason={blocked ?? acceptBlocked}>
          <Button disabled={blocked != null || acceptBlocked != null} onClick={onAccept}>
            <CheckIcon data-icon="inline-start" />
            Übernehmen
            <Kbd>A</Kbd>
          </Button>
        </Guarded>

        <Guarded reason={blocked}>
          <Button variant="destructive" disabled={blocked != null} onClick={onOpenReject}>
            <XIcon data-icon="inline-start" />
            Ablehnen
            <Kbd>R</Kbd>
          </Button>
        </Guarded>

        <Guarded reason={blocked}>
          <Button variant="outline" disabled={blocked != null} onClick={onOpenAssign}>
            <UserPlusIcon data-icon="inline-start" />
            Zuweisen
            <Kbd>Z</Kbd>
          </Button>
        </Guarded>

        <Button variant="ghost" onClick={onLater}>
          <ClockIcon data-icon="inline-start" />
          Später
          <Kbd>J</Kbd>
        </Button>
      </div>

      {noReviewer && !decided && (
        <p className="text-xs text-muted-foreground">{MISSING_REVIEWER}.</p>
      )}
    </div>
  )
}

/**
 * Tooltip an einem gesperrten Knopf. Ein `disabled` Button feuert keine
 * Zeigerereignisse – ohne diese Hülle bliebe der Grund unsichtbar.
 */
function Guarded({ reason, children }: { reason: string | null; children: ReactNode }) {
  if (reason == null) return <>{children}</>
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex">{children}</span>
      </TooltipTrigger>
      <TooltipContent>{reason}</TooltipContent>
    </Tooltip>
  )
}

function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="ml-0.5 rounded border border-current/30 px-1 font-mono text-[0.7rem] opacity-70">
      {children}
    </kbd>
  )
}
