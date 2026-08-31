import { type Dispatch, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { FilterBar } from '@/components/explorer/FilterBar'
import { FindingsTable } from '@/components/explorer/FindingsTable'
import { ReleaseGroupDialog } from '@/components/explorer/ReleaseGroupDialog'
import { RuleGroups } from '@/components/explorer/RuleGroups'
import { ReviewDrawer } from '@/components/review/ReviewDrawer'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ACTION_TYPE_LABELS } from '@/lib/labels'
import {
  companyCodeOptions,
  countByActionType,
  selectVisibleFindings,
} from '@/lib/select-findings'
import { isOpen } from '@/lib/review'
import {
  buildGroupBlock,
  buildGroupRelease,
  groupByRule,
  nextSampleStep,
  sampleForGroup,
  sampleProgress,
  type RuleGroup,
} from '@/lib/sampling'
import type { Filters } from '@/lib/select-findings'
import type { DecisionsState } from '@/state/decisions'
import type { SamplesState } from '@/state/samples'
import type { ExplorerAction, ExplorerState } from '@/state/explorer'
import { hasActiveFilters } from '@/state/explorer'
import type { DecisionRecord } from '@/types/decision'
import type { SampleReview } from '@/types/decisions-file'
import type { ActionType, Finding } from '@/types/finding'
import { ACTION_TYPES } from '@/types/finding'

/**
 * Findings-Explorer: Tabs nach Aktionstyp, Filter, Suche, Tabelle, Review-Drawer.
 *
 * Tastatur (Spec Sprint 5): `/` Suche, `J`/`K` nächstes/voriges Finding,
 * `Enter` öffnet die Karte, `Esc` schließt sie. `A`/`R`/`Z` gehören der offenen
 * Karte und liegen deshalb in `ReviewCard`.
 *
 * Im Tab Massenänderung stehen zusätzlich die Regelgruppen (Aufgabe 7): dort wird
 * eine Stichprobe geprüft und die Gruppe als Ganzes freigegeben. Läuft eine
 * Stichprobe, führen `J`/`K` und der Sprung nach einer Entscheidung durch sie
 * hindurch – nicht durch die ganze Liste.
 */
/** Standzeit der kurzen Hinweise („Filter zurückgesetzt", Ausgang der Stichprobe). */
const NOTICE_MS = 6000

export function FindingsExplorer({
  findings,
  decisions,
  samples,
  reviewer,
  state,
  dispatch,
  onDecide,
  onClearDecision,
  onSampleOutcome,
}: {
  findings: Finding[]
  decisions: DecisionsState
  samples: SamplesState
  reviewer: string
  state: ExplorerState
  dispatch: Dispatch<ExplorerAction>
  onDecide: (record: DecisionRecord) => void
  onClearDecision: (findingId: string) => void
  /** Ausgang einer Stichprobe: der Satz und – bei Freigabe – ihre Entscheidungen. */
  onSampleOutcome: (review: SampleReview, records: readonly DecisionRecord[]) => void
}) {
  const searchRef = useRef<HTMLInputElement>(null)
  /** Wartet auf die Bestätigung der Gruppenfreigabe. */
  const [releasePrompt, setReleasePrompt] = useState<{ ruleId: string; ids: string[] } | null>(
    null,
  )
  /** Warum eine Stichprobe ohne Freigabe endete – der gesperrte Fall steht dauerhaft am Rand. */
  const [sampleNotice, setSampleNotice] = useState<string | null>(null)

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
  /** Offen heißt: noch keine Entscheidung. Grundlage für den Sprung nach einer Aktion. */
  const openIds = useMemo(
    () => visible.filter(isOpen).map((finding) => finding.finding_id),
    [visible],
  )
  /** Regelgruppen über den ganzen Tab – ein Filter ist eine Sicht, kein anderer Befund. */
  const groups = useMemo(
    () => groupByRule(findings.filter((finding) => finding.action_type === 'mass_change')),
    [findings],
  )
  const groupOf = useCallback(
    (ruleId: string): RuleGroup | undefined =>
      groups.find((group) => group.rule_id === ruleId),
    [groups],
  )

  /**
   * Nach jeder Entscheidung geht es zum nächsten offenen Finding (Spec Aufgabe 3).
   * Das gerade entschiedene ist hier noch als offen gelistet – die neuen Findings
   * kommen erst mit dem nächsten Rendern – deshalb wird es ausdrücklich entfernt.
   *
   * In einer Stichprobe entscheidet dagegen ihr Stand, wie es weitergeht: eine
   * Ablehnung sperrt die Gruppe sofort, sonst geht es bis zum letzten gezogenen
   * Finding und dann in die Rückfrage.
   */
  const decide = useCallback(
    (record: DecisionRecord) => {
      onDecide(record)
      const run = state.sample
      if (run == null) {
        dispatch({
          type: 'advance',
          visibleIds,
          openIds: openIds.filter((id) => id !== record.finding_id),
        })
        return
      }

      const group = groupOf(run.ruleId)
      if (group == null) {
        dispatch({ type: 'end_sample' })
        return
      }
      // Der eigene Zustand hinkt in diesem Aufruf noch eine Entscheidung hinterher.
      const progress = sampleProgress(run.ids, { ...decisions, [record.finding_id]: record })

      switch (nextSampleStep(progress)) {
        case 'continue':
          dispatch({ type: 'sample_step', delta: 1 })
          return

        case 'blocked':
          // Die Sperre steht danach dauerhaft an der Gruppe – kein flüchtiger Hinweis.
          onSampleOutcome(
            buildGroupBlock(group, run.ids, progress.rejectedId ?? '', reviewer),
            [],
          )
          dispatch({ type: 'end_sample' })
          setSampleNotice(null)
          return

        case 'release':
          dispatch({ type: 'end_sample' })
          setReleasePrompt({ ruleId: run.ruleId, ids: [...run.ids] })
          return

        case 'incomplete':
          dispatch({ type: 'end_sample' })
          setSampleNotice(
            `Stichprobe ${run.ruleId}: ${progress.accepted} von ${progress.size} übernommen, ` +
              `${progress.assigned} zugewiesen. Ohne vollständige Übernahme gibt es keine ` +
              `Gruppenfreigabe – die Zuweisung zuerst klären.`,
          )
          return
      }
    },
    [decisions, dispatch, groupOf, onDecide, onSampleOutcome, openIds, reviewer, state.sample, visibleIds],
  )

  const startSample = useCallback(
    (group: RuleGroup) => {
      const ids = sampleForGroup(group)
      if (ids.length === 0) return
      setSampleNotice(null)
      dispatch({ type: 'start_sample', ruleId: group.rule_id, ids })
    },
    [dispatch],
  )

  const confirmRelease = useCallback(() => {
    if (releasePrompt == null) return
    const group = groupOf(releasePrompt.ruleId)
    setReleasePrompt(null)
    if (group == null) return
    const { review, records } = buildGroupRelease(
      group,
      releasePrompt.ids,
      decisions,
      reviewer,
    )
    onSampleOutcome(review, records)
  }, [decisions, groupOf, onSampleOutcome, releasePrompt, reviewer])

  /**
   * Kurze Hinweise verschwinden von selbst: sie gehören zu einer Handlung, nicht
   * zur Ansicht. Der gesperrte Fall steht dauerhaft an der Regelgruppe.
   */
  useEffect(() => {
    if (!state.filtersResetNotice) return
    const timer = setTimeout(() => dispatch({ type: 'dismiss_notice' }), NOTICE_MS)
    return () => clearTimeout(timer)
  }, [dispatch, state.filtersResetNotice])

  useEffect(() => {
    if (sampleNotice == null) return
    const timer = setTimeout(() => setSampleNotice(null), NOTICE_MS)
    return () => clearTimeout(timer)
  }, [sampleNotice])

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

  const run = state.sample

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
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

      {state.tab === 'mass_change' && (
        <RuleGroups
          groups={groups}
          samples={samples}
          reviewer={reviewer}
          onStartSample={startSample}
        />
      )}

      {sampleNotice && (
        <p role="status" className="text-xs text-muted-foreground">
          {sampleNotice}
        </p>
      )}

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

      {state.filtersResetNotice && (
        <p role="status" className="-mt-2 text-xs text-muted-foreground">
          Filter zurückgesetzt, damit das Finding aus dem Dashboard in der Liste steht.
        </p>
      )}

      {visible.length > 0 ? (
        <FindingsTable
          findings={visible}
          decisions={decisions}
          sort={state.sort}
          selectedId={state.selectedId}
          onSelect={(findingId) => dispatch({ type: 'select', findingId })}
          onOpen={(findingId) => dispatch({ type: 'open_drawer', findingId })}
          onToggleSort={(column) => dispatch({ type: 'toggle_sort', column })}
        />
      ) : (
        // Im leeren Tab Massenänderung sagen die Regelgruppen es bereits – zweimal
        // derselbe Satz wäre nur lauter, nicht klarer.
        (state.tab !== 'mass_change' || totalInTab > 0) && (
          <EmptyState tab={state.tab} filtered={totalInTab > 0} />
        )
      )}

      <p className="text-xs text-muted-foreground">
        Tastatur: <Kbd>J</Kbd> / <Kbd>K</Kbd> nächstes bzw. voriges Finding,{' '}
        <Kbd>Enter</Kbd> öffnet die Karte, <Kbd>Esc</Kbd> schließt sie, <Kbd>/</Kbd> Suche.
        In der Karte: <Kbd>A</Kbd> übernehmen, <Kbd>R</Kbd> ablehnen, <Kbd>Z</Kbd> zuweisen.
      </p>

      <ReviewDrawer
        finding={selected}
        decision={selected == null ? undefined : decisions[selected.finding_id]}
        reviewer={reviewer}
        open={state.drawerOpen}
        sample={run == null ? null : { ruleId: run.ruleId, position: run.index + 1, size: run.ids.length }}
        onOpenChange={(open) => !open && dispatch({ type: 'close_drawer' })}
        onDecide={decide}
        onClearDecision={onClearDecision}
        onLater={() =>
          run == null
            ? dispatch({ type: 'advance', visibleIds, openIds })
            : dispatch({ type: 'sample_step', delta: 1 })
        }
        onMove={(delta) =>
          run == null
            ? dispatch({ type: 'move', delta, visibleIds })
            : dispatch({ type: 'sample_step', delta })
        }
      />

      <ReleaseGroupDialog
        group={releasePrompt == null ? null : (groupOf(releasePrompt.ruleId) ?? null)}
        sampleSize={releasePrompt?.ids.length ?? 0}
        onConfirm={confirmRelease}
        onCancel={() => setReleasePrompt(null)}
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
    </p>
  )
}
