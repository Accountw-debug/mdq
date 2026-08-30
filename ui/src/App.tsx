import { useCallback, useEffect, useReducer, useState } from 'react'
import { AppShell, Placeholder, type View } from '@/components/AppShell'
import { FindingsExplorer } from '@/components/explorer/FindingsExplorer'
import { type LoadedRun, loadRunFromBuild, loadRunFromFile } from '@/lib/load-run'
import { INITIAL_EXPLORER_STATE, explorerReducer } from '@/state/explorer'

/**
 * Hält die geladenen Findings und den Zustand der beiden Ansichten.
 *
 * Der Explorer-Zustand liegt hier und nicht im Explorer, damit Filter und Auswahl
 * einen Wechsel auf Dashboard und zurück überleben.
 */
function App() {
  const [loaded, setLoaded] = useState<LoadedRun | null>(null)
  const [fatalError, setFatalError] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [view, setView] = useState<View>('findings')
  const [explorer, dispatch] = useReducer(explorerReducer, INITIAL_EXPLORER_STATE)

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
    >
      {view === 'findings' && (
        <FindingsExplorer findings={loaded.findings} state={explorer} dispatch={dispatch} />
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
