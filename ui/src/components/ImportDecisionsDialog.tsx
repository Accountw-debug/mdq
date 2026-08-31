import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { describeImport, type ImportReport } from '@/lib/decisions-io'

/**
 * Rückfrage, bevor eine Entscheidungsdatei den Stand dieser Sitzung ersetzt
 * (Freigabe Victor, 2026-08-30). Sie erscheint nur, wenn hier schon entschieden
 * wurde – ohne lokale Entscheidungen gibt es nichts zu verlieren.
 *
 * Der Bericht steht **vor** der Übernahme in der Rückfrage: wie viele Sätze die
 * Datei hat, wie viele davon ein Finding im geladenen Lauf finden, und ob sie
 * überhaupt zu diesem Lauf gehört.
 */
export function ImportDecisionsDialog({
  report,
  localCount,
  onConfirm,
  onCancel,
}: {
  report: ImportReport | null
  localCount: number
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <Dialog open={report != null} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Entscheidungen ersetzen?</DialogTitle>
          <DialogDescription>
            In dieser Sitzung {localCount === 1 ? 'liegt 1 Entscheidung' : `liegen ${localCount} Entscheidungen`}{' '}
            vor. Die Datei ersetzt sie – zusammengeführt wird nicht. Wer den bisherigen
            Stand behalten will, bricht ab und sichert ihn zuerst.
          </DialogDescription>
        </DialogHeader>

        {report != null && (
          <ul className="flex flex-col gap-1 text-xs text-muted-foreground">
            {describeImport(report).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            Abbrechen
          </Button>
          <Button onClick={onConfirm}>Ersetzen</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
