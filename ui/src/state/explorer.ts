/**
 * Zustand des Findings-Explorers: Tab, Filter, Suche, Sortierung, Auswahl, Drawer.
 *
 * Bewusst ein `useReducer` ohne State-Framework (Spec Sprint 5) und ohne React-Import,
 * damit die Übergänge unter Vitest in der Node-Umgebung geprüft werden können.
 * Die Findings selbst liegen nicht im Zustand – für `J`/`K` bekommt der Reducer die
 * gerade sichtbaren IDs mit der Aktion.
 */

import type { Filters, Sort, SortColumn, SortDirection } from '@/lib/select-findings'
import { DEFAULT_SORT, EMPTY_FILTERS } from '@/lib/select-findings'
import type { ActionType } from '@/types/finding'

/**
 * Ein laufender Stichproben-Durchgang (Spec Sprint 5, Aufgabe 7): die gezogenen
 * Findings und die Stelle, an der der Bearbeiter gerade steht. Solange er läuft,
 * führen `J`/`K` und der Sprung nach einer Entscheidung durch die Stichprobe,
 * nicht durch die ganze Liste.
 */
export interface SampleRun {
  ruleId: string
  ids: readonly string[]
  index: number
}

export interface ExplorerState {
  tab: ActionType
  filters: Filters
  search: string
  sort: Sort
  /** Zeile unter der Tastaturmarke; `null`, solange nichts gewählt ist. */
  selectedId: string | null
  drawerOpen: boolean
  /**
   * Ein Sprung aus dem Dashboard hat eine eingestellte Filterung verworfen.
   * Der Explorer zeigt dafür einen dezenten Hinweis (Freigabe Victor, 2026-08-30);
   * die nächste Handlung des Bearbeiters räumt ihn weg.
   */
  filtersResetNotice: boolean
  /** `null`, solange keine Stichprobe geprüft wird. */
  sample: SampleRun | null
}

export const INITIAL_EXPLORER_STATE: ExplorerState = {
  tab: 'review',
  filters: EMPTY_FILTERS,
  search: '',
  sort: DEFAULT_SORT,
  selectedId: null,
  drawerOpen: false,
  filtersResetNotice: false,
  sample: null,
}

export type ExplorerAction =
  | { type: 'set_tab'; tab: ActionType }
  | { type: 'set_filter'; key: keyof Filters; value: string }
  | { type: 'reset_filters' }
  | { type: 'set_search'; search: string }
  | { type: 'toggle_sort'; column: SortColumn }
  | { type: 'select'; findingId: string | null }
  | { type: 'move'; delta: number; visibleIds: readonly string[] }
  | { type: 'open_drawer'; findingId?: string }
  | { type: 'close_drawer' }
  /**
   * Sprung aus dem Dashboard auf ein bestimmtes Finding: Tab, Filter, Suche und
   * Auswahl in einem Schritt, damit die Karte nie zu einer Zeile gehört, die die
   * Liste dahinter gerade wegfiltert.
   */
  | { type: 'focus_finding'; findingId: string; actionType: ActionType }
  | { type: 'dismiss_notice' }
  /** Stichprobe einer Regelgruppe beginnen; die Karte öffnet beim ersten Finding. */
  | { type: 'start_sample'; ruleId: string; ids: readonly string[] }
  /** Innerhalb der Stichprobe weiter oder zurück; an den Rändern bleibt es stehen. */
  | { type: 'sample_step'; delta: number }
  /** Stichprobe beenden – abgebrochen, gesperrt oder durchgelaufen. */
  | { type: 'end_sample' }
  /** Nach einer Entscheidung: weiter zum nächsten offenen Finding. */
  | { type: 'advance'; visibleIds: readonly string[]; openIds: readonly string[] }

/** Spalten, bei denen „viel zuerst" die nützlichere erste Sortierung ist. */
const DESCENDING_FIRST: readonly SortColumn[] = ['impact', 'severity', 'damage_class']

function firstDirection(column: SortColumn): SortDirection {
  return DESCENDING_FIRST.includes(column) ? 'desc' : 'asc'
}

/**
 * Nächste Auswahl bei `J`/`K`. Ohne gültige Auswahl beginnt die Liste vorne
 * bzw. hinten; an den Rändern bleibt die Marke stehen, statt umzuspringen.
 */
function moveSelection(
  selectedId: string | null,
  visibleIds: readonly string[],
  delta: number,
): string | null {
  if (visibleIds.length === 0) return null
  const current = selectedId == null ? -1 : visibleIds.indexOf(selectedId)
  if (current === -1) return delta >= 0 ? visibleIds[0] : visibleIds[visibleIds.length - 1]
  const next = Math.min(Math.max(current + delta, 0), visibleIds.length - 1)
  return visibleIds[next]
}

/**
 * Nächstes offenes Finding nach der Auswahl. Ist hinter der Marke keins mehr offen,
 * beginnt die Suche wieder oben – so bleibt nichts liegen, was übersprungen wurde.
 * `null` heißt: in dieser Ansicht ist nichts mehr offen.
 */
export function nextOpenId(
  selectedId: string | null,
  visibleIds: readonly string[],
  openIds: readonly string[],
): string | null {
  const open = new Set(openIds)
  const current = selectedId == null ? -1 : visibleIds.indexOf(selectedId)
  for (let i = current + 1; i < visibleIds.length; i++) {
    if (open.has(visibleIds[i])) return visibleIds[i]
  }
  for (let i = 0; i <= current && i < visibleIds.length; i++) {
    if (open.has(visibleIds[i])) return visibleIds[i]
  }
  return null
}

/**
 * Jede Änderung an Tab, Filter oder Suche setzt die Auswahl zurück: eine Marke auf
 * einer ausgeblendeten Zeile wäre unsichtbar, `J` beginnt dann wieder oben.
 */
const CLEARED_SELECTION: Pick<
  ExplorerState,
  'selectedId' | 'drawerOpen' | 'filtersResetNotice' | 'sample'
> = {
  selectedId: null,
  drawerOpen: false,
  filtersResetNotice: false,
  // Ein Tab- oder Filterwechsel bricht eine laufende Stichprobe ab: sie gehört zu
  // einer Regelgruppe, nicht zur Liste, die gerade zu sehen ist.
  sample: null,
}

export function explorerReducer(state: ExplorerState, action: ExplorerAction): ExplorerState {
  switch (action.type) {
    case 'set_tab':
      if (action.tab === state.tab) return state
      return { ...state, tab: action.tab, ...CLEARED_SELECTION }

    case 'set_filter':
      if (state.filters[action.key] === action.value) return state
      return {
        ...state,
        filters: { ...state.filters, [action.key]: action.value },
        ...CLEARED_SELECTION,
      }

    case 'reset_filters':
      return { ...state, filters: EMPTY_FILTERS, search: '', ...CLEARED_SELECTION }

    case 'set_search':
      if (action.search === state.search) return state
      return { ...state, search: action.search, ...CLEARED_SELECTION }

    case 'toggle_sort':
      return {
        ...state,
        sort:
          state.sort.column === action.column
            ? { column: action.column, direction: state.sort.direction === 'asc' ? 'desc' : 'asc' }
            : { column: action.column, direction: firstDirection(action.column) },
      }

    case 'select':
      if (action.findingId === state.selectedId) return state
      return { ...state, selectedId: action.findingId }

    case 'move': {
      const next = moveSelection(state.selectedId, action.visibleIds, action.delta)
      if (next === state.selectedId) return state
      return { ...state, selectedId: next }
    }

    case 'open_drawer': {
      const findingId = action.findingId ?? state.selectedId
      if (findingId == null) return state
      return { ...state, selectedId: findingId, drawerOpen: true }
    }

    case 'advance': {
      const next = nextOpenId(state.selectedId, action.visibleIds, action.openIds)
      // Nichts mehr offen: die Karte schließt, die Marke bleibt auf dem letzten Finding.
      if (next == null) return state.drawerOpen ? { ...state, drawerOpen: false } : state
      return { ...state, selectedId: next, drawerOpen: true }
    }

    case 'focus_finding':
      return {
        ...state,
        tab: action.actionType,
        filters: EMPTY_FILTERS,
        search: '',
        selectedId: action.findingId,
        drawerOpen: true,
        sample: null,
        // Nur melden, was tatsächlich verworfen wurde.
        filtersResetNotice: hasActiveFilters(state),
      }

    case 'dismiss_notice':
      if (!state.filtersResetNotice) return state
      return { ...state, filtersResetNotice: false }

    case 'start_sample': {
      if (action.ids.length === 0) return state
      return {
        ...state,
        selectedId: action.ids[0],
        drawerOpen: true,
        sample: { ruleId: action.ruleId, ids: action.ids, index: 0 },
      }
    }

    case 'sample_step': {
      const run = state.sample
      if (run == null) return state
      const index = Math.min(Math.max(run.index + action.delta, 0), run.ids.length - 1)
      if (index === run.index) return state
      return { ...state, selectedId: run.ids[index], sample: { ...run, index } }
    }

    case 'end_sample':
      if (state.sample == null) return state
      // Die Marke bleibt auf dem zuletzt geprüften Finding stehen.
      return { ...state, sample: null, drawerOpen: false }

    case 'close_drawer':
      if (!state.drawerOpen) return state
      // Auswahl bleibt stehen, damit `J` dort weitermacht, wo der Drawer aufging.
      // `Esc` bricht damit auch die Stichprobe ab – ohne etwas freizugeben.
      return { ...state, drawerOpen: false, sample: null }
  }
}

/** Sind Filter oder Suche aktiv? Steuert den Knopf „Filter zurücksetzen". */
export function hasActiveFilters(state: ExplorerState): boolean {
  return (
    state.search.trim() !== '' ||
    (Object.keys(state.filters) as (keyof Filters)[]).some(
      (key) => state.filters[key] !== EMPTY_FILTERS[key],
    )
  )
}
