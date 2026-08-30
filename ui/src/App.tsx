import { useCallback, useEffect, useMemo, useReducer, useState } from 'react'
import { AppShell, Placeholder, type View } from '@/components/AppShell'
import { FindingsExplorer } from '@/components/explorer/FindingsExplorer'
import { type LoadedRun, loadRunFromBuild, loadRunFromFile } from '@/lib/load-run'
import { NO_DECISIONS, applyDecisions, decisionsReducer } from '@/state/decisions'
import { INITIAL_EXPLORER_STATE, explorerReducer } from '@/state/explorer'
import type { DecisionRecord } from '@/types/decision'

/**
 * Hält die geladenen Findings und den Zustand der beiden Ansichten.
 *
 * Der Explorer-Zustand liegt hier und nicht im Explorer, damit Filter und Auswahl
 * einen Wechsel auf Dashboard und zurück überleben. Ebenso die Entscheidungen: sie
 * gehören zur Sitzung, nicht zu einer Ansicht, und werden in Aufgabe 7 exportiert.
 */
function App() {
  const [loaded, setLoaded] = useState<LoadedRun | null>(null)
  const [fatalError, setFatalError] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [view, setView] = useState<View>('findings')
  const [explorer, dispatch] = useReducer(explorerReducer, INITIAL_EXPLORER_STATE)
  const [decisions, dispatchDecisions] = useReducer(decisionsReducer, NO_DECISIONS)
  /** `decision.by` ist im Schema Pflicht – ohne Namen keine Entscheidung. */
  const [reviewer, setReviewer] = useState('')

  // Die Liste zeigt die Findings des Laufs mit den Entscheidungen dieser Sitzung
  // darüber; die geladenen Daten selbst bleiben unverändert (CLAUDE.md, Regel 3).
  const findings = useMemo(
    () => (loaded == null ? [] : applyDecisions(loaded.findings, decisions)),
    [loaded, decisions],
  )

  const onDecide = useCallback((record: DecisionRecord) => {
    dispatchDecisions({ type: 'record', record })
  }, [])

  const onClearDecision = useCallback((findingId: string) => {
    dispatchDecisions({ type: 'clear', findingId })
  }, [])

  useEffect(() => {
    let active = true
    loadRunFromBuild()
      .then((run) => active && setLoaded(run))
      .catch((cause: unknown) => active && setFatalError((cause as Error).message))
    return () => {
      active = false
    }
  }, [])

  const onSelectFile = useCallback((file: File) => {
    loadRunFromFile(file)
      .then((run) => {
        setLoaded(run)
        setLoadError(null)
        dispatch({ type: 'reset_filters' })
        // Entscheidungen gehören zu einem Lauf; ein neuer Lauf beginnt ohne sie.
        dispatchDecisions({ type: 'reset' })
      })
      .catch((cause: unknown) => setLoadError((cause as Error).message))
  }, [])

  if (fatalError) {
    return (
      <main className="p-8">
        <p className="text-destructive">Findings konnten nicht geladen werden: {fatalError}</p>
      </main>
    )
  }

  if (!loaded) {
    return (
      <main className="p-8">
        <p className="text-muted-foreground">Findings werden geladen …</p>
      </main>
    )
  }

  return (
    <AppShell
      run={loaded.run}
      source={loaded.source}
      onSelectFile={onSelectFile}
      loadError={loadError}
      view={view}
      onViewChange={setView}
      reviewer={reviewer}
      onReviewerChange={setReviewer}
    >
      {view === 'findings' && (
        <FindingsExplorer
          findings={findings}
          decisions={decisions}
          reviewer={reviewer}
          state={explorer}
          dispatch={dispatch}
          onDecide={onDecide}
          onClearDecision={onClearDecision}
        />
      )}
      {view === 'dashboard' && (
        <Placeholder
          title="Dashboard"
          hint="Kacheln, Verteilung nach Stufe und Top 10 nach Euro-Wirkung folgen in Aufgabe 6."
        />
      )}
      {view === 'rules' && (
        <Placeholder
          title="Regeln"
          hint="Der Regelkatalog gehört nicht zu Sprint 5. Bis dahin steht die Regel-ID in jeder Zeile und im Kopf der Review-Karte."
        />
      )}
    </AppShell>
  )
}

export default App
