import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { AppShell, Placeholder, type View } from '@/components/AppShell'
import { ImportDecisionsDialog } from '@/components/ImportDecisionsDialog'
import { Dashboard } from '@/components/dashboard/Dashboard'
import { FindingsExplorer } from '@/components/explorer/FindingsExplorer'
import { DEFAULT_SOURCE, type FindingsSource, type LoadedRun, fileSource } from '@/sources'
import {
  buildDecisionsFile,
  decisionsFileName,
  describeImport,
  parseDecisionsFile,
  serializeDecisionsFile,
  type ImportReport,
} from '@/lib/decisions-io'
import { buildCleanupCsv, cleanupFileName, cleanupFindings } from '@/lib/cleanup-csv'
import { NO_DECISIONS, applyDecisions, decisionsReducer, type DecisionsState } from '@/state/decisions'
import { NO_SAMPLES, samplesReducer, type SamplesState } from '@/state/samples'
import { INITIAL_EXPLORER_STATE, explorerReducer } from '@/state/explorer'
import type { DecisionRecord } from '@/types/decision'
import type { SampleReview } from '@/types/decisions-file'
import type { Finding } from '@/types/finding'

interface Loaded {
  source: FindingsSource
  run: LoadedRun
}

/**
 * Hält die geladenen Findings und den Zustand der beiden Ansichten.
 *
 * Woher die Findings kommen, weiß nur die `FindingsSource` (`@/sources`) – hier steht
 * nur, welche gerade gilt. Der Explorer-Zustand liegt ebenfalls hier und nicht im
 * Explorer, damit Filter und Auswahl einen Wechsel auf Dashboard und zurück
 * überleben. Ebenso die Entscheidungen: sie gehören zur Sitzung, nicht zu einer
 * Ansicht, und werden in Aufgabe 7 exportiert.
 */
function App() {
  const [source, setSource] = useState<FindingsSource>(DEFAULT_SOURCE)
  /** Was gerade zu sehen ist – mitsamt der Quelle, aus der es stammt. */
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  const [fatalError, setFatalError] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [view, setView] = useState<View>('findings')
  const [explorer, dispatch] = useReducer(explorerReducer, INITIAL_EXPLORER_STATE)
  const [decisions, dispatchDecisions] = useReducer(decisionsReducer, NO_DECISIONS)
  /** Geprüfte Stichproben je Regelgruppe – eigener Zustand, siehe `@/state/samples`. */
  const [samples, dispatchSamples] = useReducer(samplesReducer, NO_SAMPLES)
  /** `decision.by` ist im Schema Pflicht – ohne Namen keine Entscheidung. */
  const [reviewer, setReviewer] = useState('')
  /** Ergebnis des letzten Imports: Bericht oder Fehler, beides steht im Banner. */
  const [importResult, setImportResult] = useState<
    { kind: 'error'; message: string } | { kind: 'report'; report: ImportReport } | null
  >(null)
  /**
   * Eingelesene Datei, die auf die Rückfrage wartet – sie erscheint nur, wenn in
   * dieser Sitzung schon entschieden wurde (Freigabe Victor, 2026-08-30).
   */
  const [pendingImport, setPendingImport] = useState<
    { records: DecisionsState; samples: SamplesState; report: ImportReport } | null
  >(null)

  // Die Liste zeigt die Findings des Laufs mit den Entscheidungen dieser Sitzung
  // darüber; die geladenen Daten selbst bleiben unverändert (CLAUDE.md, Regel 3).
  const findings = useMemo(
    () => (loaded == null ? [] : applyDecisions(loaded.run.findings, decisions)),
    [loaded, decisions],
  )

  const onDecide = useCallback((record: DecisionRecord) => {
    dispatchDecisions({ type: 'record', record })
  }, [])

  const onClearDecision = useCallback((findingId: string) => {
    dispatchDecisions({ type: 'clear', findingId })
  }, [])

  /**
   * Ausgang einer Stichprobe (Aufgabe 7): der Satz und, bei einer Freigabe, die
   * Entscheidungen der ganzen Gruppe. Beides in einem Zug – die Freigabe ohne
   * ihre Begründung wäre eine Reihe unerklärter Entscheidungen.
   */
  const onSampleOutcome = useCallback(
    (review: SampleReview, records: readonly DecisionRecord[]) => {
      for (const record of records) dispatchDecisions({ type: 'record', record })
      dispatchSamples({ type: 'record', review })
    },
    [],
  )

  /**
   * Klick auf ein Finding im Dashboard: hinüber in die Liste und die Karte öffnen.
   *
   * Der Reducer setzt dabei Tab, Filter und Suche in einem Schritt, damit die Zeile
   * hinter der Karte wirklich in der Liste steht – sonst liefe `J` ins Leere und die
   * Auswahl verschwände beim nächsten Filterwechsel. War eine Filterung eingestellt,
   * sagt der Explorer das als Hinweis (Freigabe Victor, 2026-08-30).
   */
  const onOpenFinding = useCallback((finding: Finding) => {
    setView('findings')
    dispatch({
      type: 'focus_finding',
      findingId: finding.finding_id,
      actionType: finding.action_type,
    })
  }, [])

  /**
   * Für die Fehlerbehandlung im Effekt: solange nichts geladen ist, ist ein Fehler
   * tödlich (leerer Bildschirm); danach bleibt der alte Lauf stehen und der Fehler
   * erscheint als Hinweis im Banner. Ein Ref, weil der Effekt nur an `source` hängt.
   */
  const loadedRef = useRef<Loaded | null>(null)
  useEffect(() => {
    loadedRef.current = loaded
  }, [loaded])

  useEffect(() => {
    const controller = new AbortController()
    source.loadRun(controller.signal).then(
      (run) => {
        if (controller.signal.aborted) return
        setLoaded({ source, run })
        setLoadError(null)
        dispatch({ type: 'reset_filters' })
        // Entscheidungen gehören zu einem Lauf; ein neuer Lauf beginnt ohne sie –
        // und ohne den Bericht des Imports, der zum alten Lauf gehörte.
        dispatchDecisions({ type: 'reset' })
        dispatchSamples({ type: 'reset' })
        setImportResult(null)
        setPendingImport(null)
      },
      (cause: unknown) => {
        if (controller.signal.aborted) return
        const message = (cause as Error).message
        if (loadedRef.current == null) setFatalError(message)
        else setLoadError(message)
      },
    )
    return () => controller.abort()
  }, [source])

  const onSelectFile = useCallback((file: File) => {
    setSource(fileSource(file))
  }, [])

  /**
   * Import übernehmen. Der Bearbeiter aus der Datei füllt das Banner nur, solange
   * dort nichts steht – ein getippter Name wird nie stillschweigend überschrieben.
   */
  const applyImport = useCallback(
    (result: { records: DecisionsState; samples: SamplesState; report: ImportReport }) => {
      dispatchDecisions({ type: 'import', records: result.records })
      dispatchSamples({ type: 'import', reviews: result.samples })
      setImportResult({ kind: 'report', report: result.report })
      setPendingImport(null)
      setReviewer((current) =>
        current.trim() === '' ? result.report.exportedBy : current,
      )
    },
    [],
  )

  const onImportDecisions = useCallback(
    (file: File) => {
      if (loaded == null) return
      file
        .text()
        .then((text) => {
          const result = parseDecisionsFile(text, loaded.run.run, loaded.run.findings)
          // Ersetzen ist endgültig, solange nichts gesichert ist – deshalb die Rückfrage.
          // Eine gesperrte Gruppe zählt mit: sie hat keine Entscheidung geschrieben
          // und ginge sonst unbemerkt verloren.
          if (Object.keys(decisions).length + Object.keys(samples).length > 0) {
            setPendingImport(result)
          }
          else applyImport(result)
        })
        .catch((cause: unknown) =>
          setImportResult({ kind: 'error', message: (cause as Error).message }),
        )
    },
    [applyImport, decisions, loaded, samples],
  )

  const onExportDecisions = useCallback(() => {
    if (loaded == null) return
    const file = buildDecisionsFile(loaded.run.run, decisions, samples, reviewer)
    downloadFile(
      decisionsFileName(loaded.run.run),
      serializeDecisionsFile(file),
      'application/json',
    )
  }, [decisions, loaded, reviewer, samples])

  /**
   * Bereinigungsliste: die übernommenen Massenänderungen als CSV. Grundlage sind
   * die Findings des Laufs, nicht die überlagerte Liste – entschieden hat, was in
   * der Entscheidungs-Map steht.
   */
  const onExportCleanup = useCallback(() => {
    if (loaded == null) return
    downloadFile(
      cleanupFileName(loaded.run.run),
      buildCleanupCsv(loaded.run.findings, decisions),
      'text/csv;charset=utf-8',
    )
  }, [decisions, loaded])

  const cleanupCount = useMemo(
    () => (loaded == null ? 0 : cleanupFindings(loaded.run.findings, decisions).length),
    [decisions, loaded],
  )

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
      run={loaded.run.run}
      source={loaded.source}
      onSelectFile={onSelectFile}
      loadError={loadError}
      view={view}
      onViewChange={setView}
      reviewer={reviewer}
      onReviewerChange={setReviewer}
      decisionsFile={{
        count: Object.keys(decisions).length,
        cleanupCount,
        onExport: onExportDecisions,
        onExportCleanup,
        onImport: onImportDecisions,
        message:
          importResult == null
            ? null
            : importResult.kind === 'error'
              ? {
                  kind: 'error',
                  lines: [`Entscheidungen nicht geladen: ${importResult.message}`],
                }
              : { kind: 'info', lines: describeImport(importResult.report) },
      }}
    >
      {view === 'findings' && (
        <FindingsExplorer
          findings={findings}
          decisions={decisions}
          samples={samples}
          reviewer={reviewer}
          state={explorer}
          dispatch={dispatch}
          onDecide={onDecide}
          onClearDecision={onClearDecision}
          onSampleOutcome={onSampleOutcome}
        />
      )}
      {view === 'dashboard' && (
        <Dashboard findings={findings} onOpenFinding={onOpenFinding} />
      )}
      {view === 'rules' && (
        <Placeholder
          title="Regeln"
          hint="Der Regelkatalog gehört nicht zu Sprint 5. Bis dahin steht die Regel-ID in jeder Zeile und im Kopf der Review-Karte."
        />
      )}

      <ImportDecisionsDialog
        report={pendingImport?.report ?? null}
        localCount={Object.keys(decisions).length}
        onConfirm={() => pendingImport != null && applyImport(pendingImport)}
        onCancel={() => setPendingImport(null)}
      />
    </AppShell>
  )
}

/**
 * Datei zum Sichern anbieten. Bewusst ohne Bibliothek und ohne Server: ein Blob,
 * ein Klick auf einen unsichtbaren Link, fertig – die Datei entsteht im Browser
 * und geht nirgendwo hin (Spec Sprint 5: kein Backend).
 */
function downloadFile(fileName: string, text: string, mimeType: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: mimeType }))
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  link.click()
  URL.revokeObjectURL(url)
}

export default App
