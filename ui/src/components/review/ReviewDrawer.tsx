import { ActionTypeBadge, DamageClassBadge, SeverityBadge, TierBadge } from '@/components/Badges'
import { Key } from '@/components/Key'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { formatEurOrNull } from '@/lib/format'
import type { Finding } from '@/types/finding'

/**
 * Review-Karte als rechter Drawer – Drawer statt Seitenwechsel (CONCEPT §9).
 *
 * Aufgabe 2 verdrahtet nur Öffnen, Schließen und den Kopf. Die Abschnitte
 * Ist|Soll, Evidenz, Euro-Wirkung, Warum/Wenn falsch, Wie beheben, Relevanz und
 * Aktionen folgen in Aufgabe 3 (docs/specs/SPRINT-5-UI.md).
 */
export function ReviewDrawer({
  finding,
  open,
  onOpenChange,
}: {
  finding: Finding | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const impact = formatEurOrNull(finding?.impact_eur?.amount)

  return (
    <Sheet open={open && finding != null} onOpenChange={onOpenChange}>
      <SheetContent className="w-full gap-0 sm:max-w-2xl">
        {finding && (
          <>
            <SheetHeader className="border-b">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <SheetTitle className="truncate">
                    {finding.entity.display_name ?? finding.entity.bp_key}
                  </SheetTitle>
                  <SheetDescription className="flex flex-wrap items-center gap-x-2 gap-y-1">
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
                  </SheetDescription>
                </div>
                {impact && (
                  <div className="shrink-0 text-right">
                    <div className="font-mono text-xl tabular-nums">{impact}</div>
                    <div className="text-xs text-muted-foreground">Euro-Wirkung</div>
                  </div>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-1.5 pt-1">
                <TierBadge tier={finding.tier} />
                <SeverityBadge severity={finding.severity} />
                <DamageClassBadge damageClass={finding.damage_class} />
                <ActionTypeBadge actionType={finding.action_type} />
              </div>
            </SheetHeader>

            <div className="flex-1 overflow-y-auto p-4">
              <p className="text-sm font-medium">{finding.title}</p>
              <p className="mt-4 rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                Die vollständige Review-Karte – Ist | Soll, Evidenz-Panel, Euro-Wirkung,
                Warum / Wenn falsch, Wie beheben, Relevanz und die Aktionen – kommt in
                Aufgabe 3. Hier stehen bislang nur Kopf und Tastaturweg.
              </p>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}
