/** Übergänge des Explorer-Reducers – reine Funktion, ohne React. */
import { describe, expect, it } from 'vitest'
import { ALL, DEFAULT_SORT, EMPTY_FILTERS, NO_COMPANY_CODE } from '@/lib/select-findings'
import type { ExplorerAction, ExplorerState } from '@/state/explorer'
import {
  INITIAL_EXPLORER_STATE,
  explorerReducer,
  hasActiveFilters,
  nextOpenId,
} from '@/state/explorer'

const IDS = ['F-000000000001', 'F-000000000002', 'F-000000000003']

function reduce(state: ExplorerState, ...actions: ExplorerAction[]): ExplorerState {
  return actions.reduce(explorerReducer, state)
}

describe('Ausgangszustand', () => {
  it('startet im Tab Review, ohne Filter, nach Euro-Wirkung sortiert', () => {
    expect(INITIAL_EXPLORER_STATE.tab).toBe('review')
    expect(INITIAL_EXPLORER_STATE.filters).toEqual(EMPTY_FILTERS)
    expect(INITIAL_EXPLORER_STATE.sort).toEqual(DEFAULT_SORT)
    expect(INITIAL_EXPLORER_STATE.selectedId).toBeNull()
    expect(INITIAL_EXPLORER_STATE.drawerOpen).toBe(false)
  })
})

describe('Tab, Filter und Suche', () => {
  it('setzt beim Tabwechsel die Auswahl zurück', () => {
    const state = reduce(
      INITIAL_EXPLORER_STATE,
      { type: 'select', findingId: IDS[1] },
      { type: 'set_tab', tab: 'decision' },
    )
    expect(state.tab).toBe('decision')
    expect(state.selectedId).toBeNull()
  })

  it('lässt den Zustand unberührt, wenn derselbe Tab gewählt wird', () => {
    const withSelection = explorerReducer(INITIAL_EXPLORER_STATE, {
      type: 'select',
      findingId: IDS[0],
    })
    expect(explorerReducer(withSelection, { type: 'set_tab', tab: 'review' })).toBe(withSelection)
  })

  it('setzt die Auswahl zurück, wenn ein Filter sie ausblenden könnte', () => {
    const state = reduce(
      INITIAL_EXPLORER_STATE,
      { type: 'select', findingId: IDS[0] },
      { type: 'set_filter', key: 'severity', value: 'critical' },
    )
    expect(state.filters.severity).toBe('critical')
    expect(state.selectedId).toBeNull()
  })

  it('setzt die Auswahl auch bei einer neuen Suche zurück', () => {
    const state = reduce(
      INITIAL_EXPLORER_STATE,
      { type: 'select', findingId: IDS[0] },
      { type: 'set_search', search: 'iban' },
    )
    expect(state.search).toBe('iban')
    expect(state.selectedId).toBeNull()
  })

  it('räumt mit „Filter zurücksetzen" Filter und Suche gemeinsam ab', () => {
    const state = reduce(
      INITIAL_EXPLORER_STATE,
      { type: 'set_filter', key: 'companyCode', value: NO_COMPANY_CODE },
      { type: 'set_search', search: 'müller' },
      { type: 'reset_filters' },
    )
    expect(state.filters).toEqual(EMPTY_FILTERS)
    expect(state.search).toBe('')
    expect(hasActiveFilters(state)).toBe(false)
  })

  it('erkennt aktive Filter und aktive Suche', () => {
    expect(hasActiveFilters(INITIAL_EXPLORER_STATE)).toBe(false)
    expect(
      hasActiveFilters(
        explorerReducer(INITIAL_EXPLORER_STATE, { type: 'set_filter', key: 'side', value: 'AP' }),
      ),
    ).toBe(true)
    expect(
      hasActiveFilters(
        explorerReducer(INITIAL_EXPLORER_STATE, { type: 'set_search', search: '  ' }),
      ),
    ).toBe(false)
    expect(
      hasActiveFilters(explorerReducer(INITIAL_EXPLORER_STATE, { type: 'set_search', search: 'a' })),
    ).toBe(true)
  })

  it('behält den Tab beim Zurücksetzen', () => {
    const state = reduce(
      INITIAL_EXPLORER_STATE,
      { type: 'set_tab', tab: 'process' },
      { type: 'reset_filters' },
    )
    expect(state.tab).toBe('process')
    expect(state.filters.side).toBe(ALL)
  })
})

describe('Sortierung umschalten', () => {
  it('dreht die Richtung, wenn dieselbe Spalte noch einmal geklickt wird', () => {
    const state = explorerReducer(INITIAL_EXPLORER_STATE, { type: 'toggle_sort', column: 'impact' })
    expect(state.sort).toEqual({ column: 'impact', direction: 'asc' })
  })

  it('beginnt bei Textspalten aufsteigend, bei Beträgen absteigend', () => {
    expect(
      explorerReducer(INITIAL_EXPLORER_STATE, { type: 'toggle_sort', column: 'bp_key' }).sort,
    ).toEqual({ column: 'bp_key', direction: 'asc' })
    const fromText = explorerReducer(INITIAL_EXPLORER_STATE, {
      type: 'toggle_sort',
      column: 'bp_key',
    })
    expect(explorerReducer(fromText, { type: 'toggle_sort', column: 'severity' }).sort).toEqual({
      column: 'severity',
      direction: 'desc',
    })
  })

  it('lässt die Auswahl beim Sortieren stehen', () => {
    const state = reduce(
      INITIAL_EXPLORER_STATE,
      { type: 'select', findingId: IDS[2] },
      { type: 'toggle_sort', column: 'title' },
    )
    expect(state.selectedId).toBe(IDS[2])
  })
})

describe('J und K', () => {
  it('beginnt ohne Auswahl oben bzw. unten', () => {
    expect(
      explorerReducer(INITIAL_EXPLORER_STATE, { type: 'move', delta: 1, visibleIds: IDS })
        .selectedId,
    ).toBe(IDS[0])
    expect(
      explorerReducer(INITIAL_EXPLORER_STATE, { type: 'move', delta: -1, visibleIds: IDS })
        .selectedId,
    ).toBe(IDS[2])
  })

  it('geht Schritt für Schritt durch die sichtbare Liste', () => {
    const state = reduce(
      INITIAL_EXPLORER_STATE,
      { type: 'move', delta: 1, visibleIds: IDS },
      { type: 'move', delta: 1, visibleIds: IDS },
    )
    expect(state.selectedId).toBe(IDS[1])
  })

  it('bleibt an den Rändern stehen, statt umzuspringen', () => {
    const top = reduce(
      INITIAL_EXPLORER_STATE,
      { type: 'select', findingId: IDS[0] },
      { type: 'move', delta: -1, visibleIds: IDS },
    )
    expect(top.selectedId).toBe(IDS[0])
    const bottom = reduce(
      INITIAL_EXPLORER_STATE,
      { type: 'select', findingId: IDS[2] },
      { type: 'move', delta: 1, visibleIds: IDS },
    )
    expect(bottom.selectedId).toBe(IDS[2])
  })

  it('fängt vorne an, wenn die bisherige Auswahl nicht mehr sichtbar ist', () => {
    const state = reduce(
      INITIAL_EXPLORER_STATE,
      { type: 'select', findingId: 'F-0000000000ff' },
      { type: 'move', delta: 1, visibleIds: IDS },
    )
    expect(state.selectedId).toBe(IDS[0])
  })

  it('wählt in einer leeren Liste nichts aus', () => {
    expect(
      explorerReducer(INITIAL_EXPLORER_STATE, { type: 'move', delta: 1, visibleIds: [] }).selectedId,
    ).toBeNull()
  })
})

describe('Drawer', () => {
  it('öffnet mit der übergebenen Zeile und merkt sie sich', () => {
    const state = explorerReducer(INITIAL_EXPLORER_STATE, {
      type: 'open_drawer',
      findingId: IDS[1],
    })
    expect(state.drawerOpen).toBe(true)
    expect(state.selectedId).toBe(IDS[1])
  })

  it('öffnet mit Enter die aktuelle Auswahl', () => {
    const state = reduce(
      INITIAL_EXPLORER_STATE,
      { type: 'move', delta: 1, visibleIds: IDS },
      { type: 'open_drawer' },
    )
    expect(state.drawerOpen).toBe(true)
    expect(state.selectedId).toBe(IDS[0])
  })

  it('öffnet ohne Auswahl nicht', () => {
    expect(explorerReducer(INITIAL_EXPLORER_STATE, { type: 'open_drawer' })).toBe(
      INITIAL_EXPLORER_STATE,
    )
  })

  it('behält die Auswahl beim Schließen, damit J dort weitermacht', () => {
    const state = reduce(
      INITIAL_EXPLORER_STATE,
      { type: 'open_drawer', findingId: IDS[1] },
      { type: 'close_drawer' },
    )
    expect(state.drawerOpen).toBe(false)
    expect(state.selectedId).toBe(IDS[1])
  })
})

describe('Weiter zum nächsten offenen Finding', () => {
  it('springt hinter der Auswahl auf das nächste offene', () => {
    expect(nextOpenId(IDS[0], IDS, [IDS[1], IDS[2]])).toBe(IDS[1])
    expect(nextOpenId(IDS[0], IDS, [IDS[2]])).toBe(IDS[2])
  })

  it('beginnt ohne Auswahl vorn', () => {
    expect(nextOpenId(null, IDS, IDS)).toBe(IDS[0])
  })

  it('beginnt wieder oben, wenn hinter der Auswahl nichts offen ist', () => {
    expect(nextOpenId(IDS[2], IDS, [IDS[0]])).toBe(IDS[0])
  })

  it('gibt null zurück, wenn nichts mehr offen ist', () => {
    expect(nextOpenId(IDS[1], IDS, [])).toBeNull()
  })

  it('hält die Karte offen und rückt weiter', () => {
    const state = reduce(
      INITIAL_EXPLORER_STATE,
      { type: 'open_drawer', findingId: IDS[0] },
      // Über IDS[0] wurde gerade entschieden, es zählt nicht mehr als offen.
      { type: 'advance', visibleIds: IDS, openIds: [IDS[1], IDS[2]] },
    )
    expect(state.selectedId).toBe(IDS[1])
    expect(state.drawerOpen).toBe(true)
  })

  it('schließt die Karte, wenn in dieser Ansicht nichts mehr offen ist', () => {
    const state = reduce(
      INITIAL_EXPLORER_STATE,
      { type: 'open_drawer', findingId: IDS[2] },
      { type: 'advance', visibleIds: IDS, openIds: [] },
    )
    expect(state.drawerOpen).toBe(false)
    expect(state.selectedId).toBe(IDS[2])
  })
})

describe('Sprung aus dem Dashboard', () => {
  it('setzt Tab, Auswahl und Karte in einem Schritt', () => {
    const state = explorerReducer(INITIAL_EXPLORER_STATE, {
      type: 'focus_finding',
      findingId: IDS[1],
      actionType: 'process',
    })
    expect(state.tab).toBe('process')
    expect(state.selectedId).toBe(IDS[1])
    expect(state.drawerOpen).toBe(true)
  })

  it('räumt Filter und Suche weg, damit die Zeile in der Liste steht', () => {
    const state = reduce(
      INITIAL_EXPLORER_STATE,
      { type: 'set_filter', key: 'severity', value: 'low' },
      { type: 'set_search', search: 'müller' },
      { type: 'focus_finding', findingId: IDS[0], actionType: 'review' },
    )
    expect(state.filters).toEqual(EMPTY_FILTERS)
    expect(state.search).toBe('')
    expect(state.selectedId).toBe(IDS[0])
  })

  it('meldet nur eine Filterung, die es wirklich gab', () => {
    const ohneFilter = explorerReducer(INITIAL_EXPLORER_STATE, {
      type: 'focus_finding',
      findingId: IDS[0],
      actionType: 'review',
    })
    expect(ohneFilter.filtersResetNotice).toBe(false)

    const mitFilter = reduce(
      INITIAL_EXPLORER_STATE,
      { type: 'set_filter', key: 'tier', value: 'B' },
      { type: 'focus_finding', findingId: IDS[0], actionType: 'review' },
    )
    expect(mitFilter.filtersResetNotice).toBe(true)
  })

  it('nimmt den Hinweis bei der nächsten Handlung zurück', () => {
    const withNotice = reduce(
      INITIAL_EXPLORER_STATE,
      { type: 'set_search', search: 'iban' },
      { type: 'focus_finding', findingId: IDS[0], actionType: 'review' },
    )
    expect(withNotice.filtersResetNotice).toBe(true)
    expect(explorerReducer(withNotice, { type: 'dismiss_notice' }).filtersResetNotice).toBe(false)
    expect(
      explorerReducer(withNotice, { type: 'set_filter', key: 'side', value: 'AP' })
        .filtersResetNotice,
    ).toBe(false)
    expect(
      explorerReducer(withNotice, { type: 'set_tab', tab: 'decision' }).filtersResetNotice,
    ).toBe(false)
  })
})

describe('Stichproben-Durchgang', () => {
  const start: ExplorerAction = {
    type: 'start_sample',
    ruleId: 'AR-CMP-001',
    ids: [IDS[0], IDS[1]],
  }

  it('öffnet die Karte beim ersten gezogenen Finding', () => {
    const state = explorerReducer(INITIAL_EXPLORER_STATE, start)
    expect(state.sample).toEqual({ ruleId: 'AR-CMP-001', ids: [IDS[0], IDS[1]], index: 0 })
    expect(state.selectedId).toBe(IDS[0])
    expect(state.drawerOpen).toBe(true)
  })

  it('beginnt ohne gezogene Findings gar nicht', () => {
    expect(
      explorerReducer(INITIAL_EXPLORER_STATE, { type: 'start_sample', ruleId: 'R', ids: [] }),
    ).toBe(INITIAL_EXPLORER_STATE)
  })

  it('führt durch die Stichprobe und bleibt an ihren Rändern stehen', () => {
    const zweites = reduce(INITIAL_EXPLORER_STATE, start, { type: 'sample_step', delta: 1 })
    expect(zweites.selectedId).toBe(IDS[1])
    // Hinter dem letzten gezogenen Finding geht es nicht weiter.
    expect(explorerReducer(zweites, { type: 'sample_step', delta: 1 })).toBe(zweites)
    const zurueck = explorerReducer(zweites, { type: 'sample_step', delta: -1 })
    expect(zurueck.selectedId).toBe(IDS[0])
    expect(explorerReducer(zurueck, { type: 'sample_step', delta: -1 })).toBe(zurueck)
  })

  it('schließt die Karte am Ende der Stichprobe, die Marke bleibt stehen', () => {
    const beendet = reduce(INITIAL_EXPLORER_STATE, start, { type: 'end_sample' })
    expect(beendet.sample).toBeNull()
    expect(beendet.drawerOpen).toBe(false)
    expect(beendet.selectedId).toBe(IDS[0])
  })

  it('bricht bei Esc und bei jedem Tab- oder Filterwechsel ab', () => {
    // Eine Stichprobe läuft im Tab Massenänderung – von dort weg bricht sie ab.
    const laufend = reduce(INITIAL_EXPLORER_STATE, { type: 'set_tab', tab: 'mass_change' }, start)
    expect(explorerReducer(laufend, { type: 'close_drawer' }).sample).toBeNull()
    expect(explorerReducer(laufend, { type: 'set_tab', tab: 'review' }).sample).toBeNull()
    expect(
      explorerReducer(laufend, { type: 'set_filter', key: 'tier', value: 'A' }).sample,
    ).toBeNull()
    expect(
      explorerReducer(laufend, {
        type: 'focus_finding',
        findingId: IDS[2],
        actionType: 'review',
      }).sample,
    ).toBeNull()
  })

  it('kennt ohne laufende Stichprobe keinen Schritt', () => {
    expect(explorerReducer(INITIAL_EXPLORER_STATE, { type: 'sample_step', delta: 1 })).toBe(
      INITIAL_EXPLORER_STATE,
    )
    expect(explorerReducer(INITIAL_EXPLORER_STATE, { type: 'end_sample' })).toBe(
      INITIAL_EXPLORER_STATE,
    )
  })
})
