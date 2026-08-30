import { ReviewCard } from '@/components/review/ReviewCard'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import type { DecisionRecord } from '@/types/decision'
import type { Finding } from '@/types/finding'

/**
 * Review-Karte als rechter Drawer – Drawer statt Seitenwechsel (CONCEPT §9).
 *
 * Diese Datei ist nur die Hülle: Öffnen, Schließen (`Esc` über Radix) und der
 * zugängliche Name. Der Inhalt steht in `ReviewCard` und hängt in keinem Portal,
 * damit der Rauchtest ihn ohne DOM-Umgebung rendern kann.
 */
export function ReviewDrawer({
  finding,
  decision,
  reviewer,
  open,
  onOpenChange,
  onDecide,
  onClearDecision,
  onLater,
  onMove,
}: {
  finding: Finding | null
  decision: DecisionRecord | undefined
  reviewer: string
  open: boolean
  onOpenChange: (open: boolean) => void
  onDecide: (record: DecisionRecord) => void
  onClearDecision: (findingId: string) => void
  onLater: () => void
  onMove: (delta: number) => void
}) {
  return (
    <Sheet open={open && finding != null} onOpenChange={onOpenChange}>
      <SheetContent className="w-full gap-0 p-0 sm:max-w-3xl">
        {finding && (
          <>
            <SheetHeader className="sr-only">
              <SheetTitle>
                Review-Karte {finding.entity.bp_key}, Regel {finding.rule_id}
              </SheetTitle>
              <SheetDescription>
                Ist und Soll, Evidenz, Euro-Wirkung, Behebung und Aktionen zu diesem Finding.
              </SheetDescription>
            </SheetHeader>
            {/* `key`: eine neue Karte beginnt ohne gewählte Option und ohne offenen Dialog. */}
            <ReviewCard
              key={finding.finding_id}
              finding={finding}
              decision={decision}
              reviewer={reviewer}
              onDecide={onDecide}
              onClearDecision={onClearDecision}
              onLater={onLater}
              onMove={onMove}
            />
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}
