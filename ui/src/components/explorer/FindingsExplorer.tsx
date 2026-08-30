import { type Dispatch, useEffect, useMemo, useRef } from 'react'
import { FilterBar } from '@/components/explorer/FilterBar'
import { FindingsTable } from '@/components/explorer/FindingsTable'
import { ReviewDrawer } from '@/components/review/ReviewDrawer'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ACTION_TYPE_LABELS } from '@/lib/labels'
import {
  companyCodeOptions,
  countByActionType,
  selectVisibleFindings,
} from '@/lib/select-findings'
import type { Filters } from '@/lib/select-findings'
import type { ExplorerAction, ExplorerState } from '@/state/explorer'
import { hasActiveFilters } from '@/state/explorer'
import type { ActionType, Finding } from '@/types/finding'
import { ACTION_TYPES } from '@/types/finding'

/**
 * Findings-Explorer: Tabs nach Aktionstyp, Filter, Suche, Tabelle, Review-Drawer.
 *
 * Tastatur (Spec Sprint 5): `/` Suche, `J`/`K` nächstes/voriges Finding,
 * `Enter` öffnet die Karte, `Esc` schließt sie. `A`/`R`/`Z` kommen mit den
 * Aktionen in Aufgabe 3.
 */
export function FindingsExplorer({
  findings,
  state,
  dispatch,
}: {
  findings: Finding[]
  state: ExplorerState
  dispatch: Dispatch<ExplorerAction>
}) {
  const searchRef = useRef<HTMLInputElement>(null)

  const counts = useMemo(
    () => countByActionType(findings, state.filters, state.search),
    [findings, state.filters, state.search],
  )
  const visible = useMemo(
    () =>
      selectVisibleFindings(findings, {
        tab: state.tab,
        filters: state.filters,
        search: state.search,
        sort: state.sort,
      }),
    [findings, state.tab, state.filters, state.search, state.sort],
  )
  const visibleIds = useMemo(() => visible.map((finding) => finding.finding_id), [visible])
  const companyCodes = useMemo(() => companyCodeOptions(findings), [findings])
  const selected = useMemo(
    () => findings.find((finding) => finding.finding_id === state.selectedId) ?? null,
    [findings, state.selectedId],
  )
  const totalInTab = useMemo(
    () => findings.filter((finding) => finding.action_type === state.tab).length,
    [findings, state.tab],
  )

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return
      const target = event.target as HTMLElement | null
      const inField =
        target != null &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable === true)

      if (event.key === '/' && !inField) {
        event.preventDefault()
        searchRef.current?.focus()
        searchRef.current?.select()
        return
      }
      if (event.key === 'Escape' && inField) {
        searchRef.current?.blur()
        return
      }
      // Im offenen Drawer gehört die Tastatur der Review-Karte (Esc schließt sie).
      if (inField || state.drawerOpen) return

      switch (event.key) {
        case 'j':
        case 'J':
          event.preventDefault()
          dispatch({ type: 'move', delta: 1, visibleIds })
          break
        case 'k':
        case 'K':
          event.preventDefault()
          dispatch({ type: 'move', delta: -1, visibleIds })
          break
        case 'Enter':
          if (state.selectedId != null) {
            event.preventDefault()
            dispatch({ type: 'open_drawer' })
          }
          break
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [dispatch, state.drawerOpen, state.selectedId, visibleIds])

  return (
    <div className="flex flex-col gap-4">
      <Tabs
        value={state.tab}
        onValueChange={(value) => dispatch({ type: 'set_tab', tab: value as ActionType })}
      >
        <TabsList>
          {ACTION_TYPES.map((actionType) => (
            <TabsTrigger key={actionType} value={actionType}>
              {ACTION_TYPE_LABELS[actionType]}
              <span className="ml-1.5 font-mono text-xs text-muted-foreground tabular-nums">
                {counts[actionType]}
              </span>
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <FilterBar
        filters={state.filters}
        search={state.search}
        companyCodes={companyCodes}
        hasActive={hasActiveFilters(state)}
        searchRef={searchRef}
        onFilterChange={(key: keyof Filters, value: string) =>
          dispatch({ type: 'set_filter', key, value })
        }
        onSearchChange={(search) => dispatch({ type: 'set_search', search })}
        onReset={() => dispatch({ type: 'reset_filters' })}
      />

      {visible.length === 0 ? (
        <EmptyState tab={state.tab} filtered={totalInTab > 0} />
      ) : (
        <FindingsTable
          findings={visible}
          sort={state.sort}
          selectedId={state.selectedId}
          onSelect={(findingId) => dispatch({ type: 'select', findingId })}
          onOpen={(findingId) => dispatch({ type: 'open_drawer', findingId })}
          onToggleSort={(column) => dispatch({ type: 'toggle_sort', column })}
        />
      )}

      <p className="text-xs text-muted-foreground">
        Tastatur: <Kbd>J</Kbd> / <Kbd>K</Kbd> nächstes bzw. voriges Finding,{' '}
        <Kbd>Enter</Kbd> öffnet die Karte, <Kbd>Esc</Kbd> schließt sie, <Kbd>/</Kbd> Suche.
      </p>

      <ReviewDrawer
        finding={selected}
        open={state.drawerOpen}
        onOpenChange={(open) => !open && dispatch({ type: 'close_drawer' })}
      />
    </div>
  )
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded border px-1 py-px font-mono text-[0.7rem] text-foreground">
      {children}
    </kbd>
  )
}

function EmptyState({ tab, filtered }: { tab: ActionType; filtered: boolean }) {
  if (filtered) {
    return (
      <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
        Keine Findings mit diesen Filtern. Filter zurücksetzen oder anderen Tab wählen.
      </p>
    )
  }
  return (
    <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
      Keine Findings vom Aktionstyp {ACTION_TYPE_LABELS[tab]} in diesem Lauf.
      {tab === 'mass_change' &&
        ' Massenänderung setzt Stufe A voraus – die Beispiel-Findings enthalten keine.'}
    </p>
  )
}
