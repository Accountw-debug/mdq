import { useEffect, useMemo, useRef } from 'react'
import { createColumnHelper, tableFeatures, useTable } from '@tanstack/react-table'
import { ChevronDownIcon, ChevronUpIcon } from 'lucide-react'
import {
  DamageClassBadge,
  SeverityBadge,
  SideBadge,
  StatusBadge,
  TierBadge,
} from '@/components/Badges'
import { Key } from '@/components/Key'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatEur } from '@/lib/format'
import type { Sort, SortColumn } from '@/lib/select-findings'
import { cn } from '@/lib/utils'
import type { Finding } from '@/types/finding'

/**
 * Findings-Tabelle. Sortiert wird **nicht** von TanStack, sondern von
 * `sortFindings`: die Reihenfolge ist damit eine reine Funktion und im Test
 * festgenagelt (CLAUDE.md, Regel 9). TanStack liefert Spaltendefinition und
 * Rendering – deshalb ist auch nur der Kern-Funktionssatz registriert.
 */

const features = tableFeatures({})
const helper = createColumnHelper<typeof features, Finding>()

/**
 * Ausrichtung und Sortierspalte je Spalte. Bewusst neben der Spaltendefinition
 * statt in `columnDef.meta`: das spart eine Modul-Erweiterung der Bibliothek.
 */
const LAYOUT: Record<string, { sortColumn: SortColumn; align?: 'right'; className?: string }> = {
  tier: { sortColumn: 'tier' },
  severity: { sortColumn: 'severity' },
  damage_class: { sortColumn: 'damage_class' },
  side: { sortColumn: 'side' },
  rule_id: { sortColumn: 'rule_id' },
  bp_key: { sortColumn: 'bp_key' },
  title: { sortColumn: 'title', className: 'max-w-[28rem] min-w-[16rem]' },
  impact: { sortColumn: 'impact', align: 'right' },
  status: { sortColumn: 'status' },
}

const columns = helper.columns([
  helper.display({
    id: 'tier',
    header: 'Stufe',
    cell: ({ row }) => <TierBadge tier={row.original.tier} />,
  }),
  helper.display({
    id: 'severity',
    header: 'Schwere',
    cell: ({ row }) => <SeverityBadge severity={row.original.severity} />,
  }),
  helper.display({
    id: 'damage_class',
    header: 'SK',
    cell: ({ row }) => <DamageClassBadge damageClass={row.original.damage_class} />,
  }),
  helper.display({
    id: 'side',
    header: 'Seite',
    cell: ({ row }) => <SideBadge side={row.original.side} />,
  }),
  helper.display({
    id: 'rule_id',
    header: 'Regel',
    cell: ({ row }) => <Key className="text-muted-foreground">{row.original.rule_id}</Key>,
  }),
  helper.display({
    id: 'bp_key',
    header: 'Geschäftspartner',
    cell: ({ row }) => (
      <div className="leading-tight">
        <Key>{row.original.entity.bp_key}</Key>
        {row.original.entity.display_name && (
          <div className="truncate text-xs text-muted-foreground">
            {row.original.entity.display_name}
          </div>
        )}
      </div>
    ),
  }),
  helper.display({
    id: 'title',
    header: 'Titel',
    cell: ({ row }) => <span className="line-clamp-2">{row.original.title ?? '—'}</span>,
  }),
  helper.display({
    id: 'impact',
    header: 'Euro-Wirkung',
    cell: ({ row }) => {
      const impact = row.original.impact_eur
      if (!impact) return <span className="text-muted-foreground">—</span>
      return <Key className="tabular-nums">{formatEur(impact.amount)}</Key>
    },
  }),
  helper.display({
    id: 'status',
    header: 'Status',
    cell: ({ row }) => <StatusBadge status={row.original.status} />,
  }),
])

export function FindingsTable({
  findings,
  sort,
  selectedId,
  onSelect,
  onOpen,
  onToggleSort,
}: {
  findings: Finding[]
  sort: Sort
  selectedId: string | null
  onSelect: (findingId: string) => void
  onOpen: (findingId: string) => void
  onToggleSort: (column: SortColumn) => void
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const data = useMemo(() => findings, [findings])
  const table = useTable({
    features,
    columns,
    data,
    getRowId: (finding) => finding.finding_id,
  })

  // Bei J/K die Marke im Blick behalten, ohne die Seite zu verschieben.
  useEffect(() => {
    if (selectedId == null) return
    containerRef.current
      ?.querySelector('[data-selected="true"]')
      ?.scrollIntoView({ block: 'nearest' })
  }, [selectedId])

  return (
    <div ref={containerRef} className="overflow-x-auto rounded-lg border">
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id}>
              {headerGroup.headers.map((header) => {
                const layout = LAYOUT[header.column.id]
                const active = sort.column === layout.sortColumn
                return (
                  <TableHead
                    key={header.id}
                    className={cn('whitespace-nowrap', layout.align === 'right' && 'text-right')}
                    aria-sort={
                      active ? (sort.direction === 'asc' ? 'ascending' : 'descending') : undefined
                    }
                  >
                    <button
                      type="button"
                      onClick={() => onToggleSort(layout.sortColumn)}
                      className={cn(
                        'inline-flex items-center gap-1 rounded-sm outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50',
                        active && 'text-foreground',
                      )}
                    >
                      <table.FlexRender header={header} />
                      {active &&
                        (sort.direction === 'asc' ? (
                          <ChevronUpIcon className="size-3" />
                        ) : (
                          <ChevronDownIcon className="size-3" />
                        ))}
                    </button>
                  </TableHead>
                )
              })}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows.map((row) => {
            const selected = row.original.finding_id === selectedId
            return (
              <TableRow
                key={row.id}
                data-selected={selected}
                aria-selected={selected}
                onClick={() => {
                  onSelect(row.original.finding_id)
                  onOpen(row.original.finding_id)
                }}
                className={cn(
                  'cursor-pointer align-top',
                  selected && 'bg-muted/70 outline -outline-offset-1 outline-ring/40',
                )}
              >
                {row.getAllCells().map((cell) => {
                  const layout = LAYOUT[cell.column.id]
                  return (
                    <TableCell
                      key={cell.id}
                      className={cn(
                        'py-2',
                        layout.align === 'right' && 'text-right',
                        layout.className,
                      )}
                    >
                      <table.FlexRender cell={cell} />
                    </TableCell>
                  )
                })}
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
