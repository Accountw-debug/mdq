import { memo, useCallback, useEffect, useMemo, useRef } from 'react'
import {
  FlexRender,
  createColumnHelper,
  tableFeatures,
  useTable,
  type Row,
} from '@tanstack/react-table'
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
import { formatMoney } from '@/lib/format'
import { decisionStatusLabel } from '@/lib/review'
import type { Sort, SortColumn } from '@/lib/select-findings'
import { indexOfId } from '@/lib/select-findings'
import { cn } from '@/lib/utils'
import type { DecisionsState } from '@/state/decisions'
import type { DecisionRecord } from '@/types/decision'
import type { Finding } from '@/types/finding'

/**
 * Findings-Tabelle. Sortiert wird **nicht** von TanStack, sondern von
 * `sortFindings`: die Reihenfolge ist damit eine reine Funktion und im Test
 * festgenagelt (CLAUDE.md, Regel 9). TanStack liefert Spaltendefinition und
 * Rendering – deshalb ist auch nur der Kern-Funktionssatz registriert.
 *
 * Der Schnitt ist auf Virtualisierung ausgelegt (ui/NOTES.md, 2026-08-30):
 * feste Zeilenhöhe (`ROW_HEIGHT`), eigener begrenzter Scrollbereich mit klebendem
 * Kopf, Zeilenzugriff über den **Index** statt über eine DOM-Suche, konstante
 * Spalten und eine gedächtnisfähige Zeile. Ein Fenster über 10.000 Findings
 * ersetzt danach nur die Schleife in `FindingsTable` – nichts sonst.
 */

/**
 * Feste Zeilenhöhe in px: jede Zeile ist genau zwei Textzeilen hoch – so hoch
 * wie die höchste Zelle (Geschäftspartner mit Schlüssel und Name, Titel mit
 * `line-clamp-2`). Der Virtualizer braucht später genau diese Konstante als
 * `estimateSize`; inhaltsabhängige Höhen müsste er messen.
 */
export const ROW_HEIGHT = 56

/**
 * Was eine Zeile zeigt: das Finding und die Entscheidung dieser Sitzung dazu.
 *
 * Die Entscheidung gehört in die Zeilendaten und **nicht** in eine Closure der
 * Spaltendefinition: sonst baut jede Entscheidung alle Spalten neu und damit die
 * ganze Tabelle. `finding.decision` reicht nicht – dort steht (schemakonform)
 * keine `action`, und der Statustext hängt daran.
 */
export interface FindingRow {
  finding: Finding
  decision: DecisionRecord | undefined
}

const features = tableFeatures({})
const helper = createColumnHelper<typeof features, FindingRow>()

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

/** Konstant – die Spalten hängen an keinem Zustand. */
const COLUMNS = helper.columns([
  helper.display({
    id: 'tier',
    header: 'Stufe',
    cell: ({ row }) => <TierBadge tier={row.original.finding.tier} />,
  }),
  helper.display({
    id: 'severity',
    header: 'Schwere',
    cell: ({ row }) => <SeverityBadge severity={row.original.finding.severity} />,
  }),
  helper.display({
    id: 'damage_class',
    header: 'SK',
    cell: ({ row }) => <DamageClassBadge damageClass={row.original.finding.damage_class} />,
  }),
  helper.display({
    id: 'side',
    header: 'Seite',
    cell: ({ row }) => <SideBadge side={row.original.finding.side} />,
  }),
  helper.display({
    id: 'rule_id',
    header: 'Regel',
    cell: ({ row }) => (
      <Key className="text-muted-foreground">{row.original.finding.rule_id}</Key>
    ),
  }),
  helper.display({
    id: 'bp_key',
    header: 'Geschäftspartner',
    cell: ({ row }) => (
      <div className="leading-tight">
        <Key>{row.original.finding.entity.bp_key}</Key>
        {row.original.finding.entity.display_name && (
          <div className="truncate text-xs text-muted-foreground">
            {row.original.finding.entity.display_name}
          </div>
        )}
      </div>
    ),
  }),
  helper.display({
    id: 'title',
    header: 'Titel',
    cell: ({ row }) => <span className="line-clamp-2">{row.original.finding.title ?? '—'}</span>,
  }),
  helper.display({
    id: 'impact',
    header: 'Euro-Wirkung',
    cell: ({ row }) => {
      const impact = row.original.finding.impact_eur
      if (!impact) return <span className="text-muted-foreground">—</span>
      return <Key className="tabular-nums">{formatMoney(impact.amount, impact.currency)}</Key>
    },
  }),
  helper.display({
    id: 'status',
    header: 'Status',
    cell: ({ row }) => {
      const { finding, decision } = row.original
      return (
        <StatusBadge
          status={finding.status}
          label={decision && decisionStatusLabel(decision)}
        />
      )
    },
  }),
])

export function FindingsTable({
  findings,
  decisions,
  sort,
  selectedId,
  onSelect,
  onOpen,
  onToggleSort,
}: {
  findings: Finding[]
  decisions: DecisionsState
  sort: Sort
  selectedId: string | null
  onSelect: (findingId: string) => void
  onOpen: (findingId: string) => void
  onToggleSort: (column: SortColumn) => void
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const data = useMemo(
    () =>
      findings.map((finding) => ({ finding, decision: decisions[finding.finding_id] })),
    [findings, decisions],
  )
  const table = useTable({
    features,
    columns: COLUMNS,
    data,
    getRowId: (row) => row.finding.finding_id,
  })

  /**
   * Zeile in den Blick holen. Der Index ist die Schnittstelle, nicht das
   * DOM-Element: mit Virtualisierung ist die gewählte Zeile womöglich gar nicht
   * gerendert, und der Virtualizer springt dann selbst an diesen Index.
   */
  const scrollToIndex = useCallback((index: number) => {
    const body = containerRef.current?.querySelector('tbody')
    body?.children[index]?.scrollIntoView({ block: 'nearest' })
  }, [])

  // Bei J/K die Marke im Blick behalten, ohne die Seite zu verschieben.
  const selectedIndex = indexOfId(findings, selectedId)
  useEffect(() => {
    if (selectedIndex >= 0) scrollToIndex(selectedIndex)
  }, [selectedIndex, scrollToIndex])

  return (
    <Table
      containerClassName="min-h-0 flex-1 rounded-lg border"
      containerRef={containerRef}
    >
      <TableHeader>
        {table.getHeaderGroups().map((headerGroup) => (
          <TableRow key={headerGroup.id}>
            {headerGroup.headers.map((header) => {
              const layout = LAYOUT[header.column.id]
              const active = sort.column === layout.sortColumn
              return (
                <TableHead
                  key={header.id}
                  // Klebender Kopf: der Scrollbereich ist der Tabellen-Container.
                  className={cn(
                    'sticky top-0 z-10 border-b bg-background whitespace-nowrap',
                    layout.align === 'right' && 'text-right',
                  )}
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
                    <FlexRender header={header} />
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
        {table.getRowModel().rows.map((row) => (
          <FindingsTableRow
            key={row.id}
            row={row}
            selected={row.original.finding.finding_id === selectedId}
            onSelect={onSelect}
            onOpen={onOpen}
          />
        ))}
      </TableBody>
    </Table>
  )
}

/**
 * Eine Zeile. `memo` lohnt sich, weil TanStack das Zeilenmodell an
 * `table.options.data` bindet: solange die sichtbare Liste dieselbe bleibt, sind
 * die Zeilenobjekte identisch, und ein Sprung mit `J`/`K` rendert nur die beiden
 * Zeilen neu, deren `selected` sich geändert hat – nicht alle.
 */
const FindingsTableRow = memo(function FindingsTableRow({
  row,
  selected,
  onSelect,
  onOpen,
}: {
  row: Row<typeof features, FindingRow>
  selected: boolean
  onSelect: (findingId: string) => void
  onOpen: (findingId: string) => void
}) {
  const findingId = row.original.finding.finding_id
  return (
    <TableRow
      data-selected={selected}
      aria-selected={selected}
      // Feste Höhe statt inhaltsabhängiger – Grundlage der Virtualisierung.
      style={{ height: ROW_HEIGHT }}
      onClick={() => {
        onSelect(findingId)
        onOpen(findingId)
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
              'overflow-hidden py-2',
              layout.align === 'right' && 'text-right',
              layout.className,
            )}
          >
            <FlexRender cell={cell} />
          </TableCell>
        )
      })}
    </TableRow>
  )
})
