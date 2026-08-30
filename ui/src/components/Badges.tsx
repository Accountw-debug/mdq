import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  ACTION_TYPE_LABELS,
  DAMAGE_CLASS_LABELS,
  SEVERITY_LABELS,
  SIDE_LABELS,
  SIDE_SHORT_LABELS,
  STATUS_LABELS,
  TIER_LABELS,
  TIER_SHORT_LABELS,
} from '@/lib/labels'
import { cn } from '@/lib/utils'
import type { ActionType, DamageClass, FindingStatus, Severity, Side, Tier } from '@/types/finding'

/**
 * Kleine Badges für Stufe, Schwere, Schadensklasse, Seite und Status.
 *
 * Farbe tragen nur die Badges selbst, nie Zeilen oder Flächen (docs/CONCEPT.md,
 * Abschnitt 9). Kritisch und Schadensklasse 1 sind die einzigen roten Töne, damit
 * Rot in einer langen Liste etwas bedeutet.
 */

const SEVERITY_CLASSES: Record<Severity, string> = {
  low: 'border-border text-muted-foreground',
  medium: 'border-border text-foreground',
  high: 'border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400',
  critical: 'border-destructive/40 bg-destructive/10 text-destructive',
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <Badge variant="outline" className={cn('font-normal', SEVERITY_CLASSES[severity])}>
      {SEVERITY_LABELS[severity]}
    </Badge>
  )
}

export function TierBadge({ tier }: { tier: Tier }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge
          variant={tier === 'decision' ? 'secondary' : 'outline'}
          className="font-mono font-normal"
        >
          {TIER_SHORT_LABELS[tier]}
        </Badge>
      </TooltipTrigger>
      <TooltipContent>Stufe {TIER_LABELS[tier]}</TooltipContent>
    </Tooltip>
  )
}

export function DamageClassBadge({ damageClass }: { damageClass: DamageClass }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge
          variant="outline"
          className={cn(
            'font-mono font-normal',
            damageClass === 1 && 'border-destructive/40 bg-destructive/10 text-destructive',
          )}
        >
          SK{damageClass}
        </Badge>
      </TooltipTrigger>
      <TooltipContent>Schadensklasse {damageClass}: {DAMAGE_CLASS_LABELS[damageClass]}</TooltipContent>
    </Tooltip>
  )
}

export function SideBadge({ side }: { side: Side }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant="outline" className="font-mono font-normal text-muted-foreground">
          {SIDE_SHORT_LABELS[side]}
        </Badge>
      </TooltipTrigger>
      <TooltipContent>{SIDE_LABELS[side]}</TooltipContent>
    </Tooltip>
  )
}

const STATUS_CLASSES: Record<FindingStatus, string> = {
  open: 'border-border text-foreground',
  in_progress: 'border-border bg-muted text-foreground',
  done: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
  accepted_risk: 'border-border text-muted-foreground',
  rejected: 'border-border text-muted-foreground line-through',
}

export function StatusBadge({ status }: { status: FindingStatus }) {
  return (
    <Badge variant="outline" className={cn('font-normal', STATUS_CLASSES[status])}>
      {STATUS_LABELS[status]}
    </Badge>
  )
}

export function ActionTypeBadge({ actionType }: { actionType: ActionType }) {
  return (
    <Badge variant="secondary" className="font-normal">
      {ACTION_TYPE_LABELS[actionType]}
    </Badge>
  )
}
