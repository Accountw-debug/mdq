import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Key } from '@/components/Key'
import type { RuleGroup } from '@/lib/sampling'

/**
 * Rückfrage vor der Gruppenfreigabe (Spec Sprint 5, Aufgabe 7).
 *
 * Sie erscheint erst, wenn jedes Finding der Stichprobe übernommen wurde. Was hier
 * bestätigt wird, ist die eine Entscheidung, die im Prototyp viele ersetzt –
 * deshalb steht davor, wie viele Findings sie trifft und welche sie ausnimmt.
 *
 * Freigegeben heißt `in Arbeit`, nicht `erledigt`: entschieden ist nicht umgesetzt
 * (Freigabe Victor, 2026-08-30).
 */
export function ReleaseGroupDialog({
  group,
  sampleSize,
  onConfirm,
  onCancel,
}: {
  group: RuleGroup | null
  sampleSize: number
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <Dialog open={group != null} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Regelgruppe freigeben?</DialogTitle>
          <DialogDescription>
            {group != null && (
              <>
                Die Stichprobe ist vollständig übernommen: {sampleSize} von {group.total}{' '}
                Findings der Regel <Key>{group.rule_id}</Key> geprüft.
              </>
            )}
          </DialogDescription>
        </DialogHeader>

        {group != null && (
          <ul className="flex list-disc flex-col gap-1 pl-4 text-xs text-muted-foreground">
            <li>
              <span className="font-mono tabular-nums">{group.releasable}</span> offene Findings
              werden übernommen und stehen danach auf „in Arbeit" – entschieden, nicht umgesetzt.
            </li>
            {group.bankData > 0 && (
              <li>
                <span className="font-mono tabular-nums">{group.bankData}</span> Findings der
                Schadensklasse 1 bleiben offen: Bankdaten werden nie über eine Gruppe entschieden.
              </li>
            )}
            <li>
              Die geprüfte Stichprobe wird in <Key>decisions.json</Key> festgehalten
              (<Key>sample_reviewed</Key>).
            </li>
          </ul>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            Abbrechen
          </Button>
          <Button onClick={onConfirm}>Gruppe freigeben</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
