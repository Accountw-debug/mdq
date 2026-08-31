import { useRef } from 'react'
import { AlertTriangleIcon, DownloadIcon, InfoIcon, UploadIcon } from 'lucide-react'
import { Key } from '@/components/Key'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { formatDate } from '@/lib/format'
import type { FindingsSource } from '@/sources'
import type { RunInfo } from '@/types/finding'

/** Sichern und Laden der Entscheidungen – als ein Bündel, damit es der Rahmen nur durchreicht. */
export interface DecisionsFileControls {
  /** Entscheidungen dieser Sitzung; bei 0 gibt es nichts zu sichern. */
  count: number
  /** Zeilen der Bereinigungsliste: übernommene Massenänderungen (Aufgabe 7). */
  cleanupCount: number
  onExport: () => void
  onExportCleanup: () => void
  onImport: (file: File) => void
  /** Ergebnis des letzten Imports – Bericht oder Fehler. */
  message: { kind: 'error' | 'info'; lines: string[] } | null
}

/**
 * Datenstand-Banner, auf jedem Screen oben (docs/CONCEPT.md, Abschnitt 9):
 * „Stand 28.08.2026 · Lauf demo-2026-08-30 · Engine 0.1.0 · Regelpaket 0.1".
 *
 * Rechts „Lauf laden": damit lässt sich `runs/<run_id>/` der Engine ohne Rebuild
 * ansehen. Gewählt werden `findings.json` und `run.json` zusammen – erst mit dem
 * Lauf-Kopf stimmen Tabellenzahl und Buchungskreise. Die Dateien werden nur im
 * Speicher gehalten – kein localStorage, nichts bleibt unbemerkt im Browser
 * liegen (Spec Sprint 5).
 *
 * Daneben steht der Bearbeiter: `decision.by` ist im Schema Pflicht, also wird der
 * Name einmal je Sitzung eingetragen und gilt für jede Entscheidung. Auch er bleibt
 * im Speicher und verschwindet mit dem Tab.
 *
 * Ebenfalls hier: Sichern und Laden der Entscheidungen (`decisions.json`, Vertrag in
 * `@/types/decisions-file`). Weil nichts im Browser liegen bleibt, ist die Datei der
 * einzige Weg, am nächsten Tag weiterzuarbeiten – sie gehört deshalb neben den
 * Datenstand und nicht in eine Ecke des Explorers.
 *
 * Daneben die Bereinigungsliste (CSV, Aufgabe 7): dieselbe Sitzung, ein anderer
 * Leser. `decisions.json` kommt hierher zurück, die Bereinigungsliste geht ins
 * SAP-Team und enthält nur die übernommenen Massenänderungen.
 */
export function DataBanner({
  run,
  source,
  onSelectFiles,
  loadError,
  reviewer,
  onReviewerChange,
  decisionsFile,
}: {
  run: RunInfo
  source: FindingsSource
  onSelectFiles: (files: File[]) => void
  loadError: string | null
  reviewer: string
  onReviewerChange: (reviewer: string) => void
  decisionsFile: DecisionsFileControls
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const decisionsInputRef = useRef<HTMLInputElement>(null)

  return (
    <div className="border-b bg-background">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-6 py-2 text-xs text-muted-foreground">
        <span>
          Stand <span className="text-foreground">{formatDate(run.data_as_of)}</span>
        </span>
        <span aria-hidden>·</span>
        <span>
          Lauf <Key className="text-foreground">{run.run_id}</Key>
        </span>
        <span aria-hidden>·</span>
        <span>Engine {run.engine_version}</span>
        <span aria-hidden>·</span>
        <span>Regelpaket {run.pack_version}</span>
        <span aria-hidden>·</span>
        <span>
          {run.company_codes.length === 0 ? (
            'ohne Buchungskreis'
          ) : (
            <>
              {run.company_codes.length === 1 ? 'Buchungskreis ' : 'Buchungskreise '}
              {run.company_codes.map((code, index) => (
                <span key={code}>
                  {index > 0 ? ', ' : ''}
                  <Key className="text-foreground">{code}</Key>
                </span>
              ))}
            </>
          )}
        </span>
        {run.tables_loaded > 0 && (
          <>
            <span aria-hidden>·</span>
            <span>{run.tables_loaded} Tabellen</span>
          </>
        )}

        <div className="ml-auto flex items-center gap-2">
          <label className="flex items-center gap-1.5">
            Bearbeiter
            <Input
              value={reviewer}
              onChange={(event) => onReviewerChange(event.target.value)}
              placeholder="Ihr Name"
              aria-label="Bearbeiter für Entscheidungen"
              className="h-6 w-36 text-xs"
            />
          </label>
          <span aria-hidden>·</span>
          <span className="hidden sm:inline">
            Quelle: {source.kind === 'file' ? <Key>{source.label}</Key> : source.label}
          </span>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept="application/json,.json"
            className="hidden"
            onChange={(event) => {
              const files = [...(event.target.files ?? [])]
              // Zurücksetzen, damit dieselbe Datei erneut gewählt werden kann.
              event.target.value = ''
              if (files.length > 0) onSelectFiles(files)
            }}
          />
          <Button
            variant="outline"
            size="xs"
            title="findings.json und run.json des Laufs zusammen wählen"
            onClick={() => inputRef.current?.click()}
          >
            <UploadIcon data-icon="inline-start" />
            Findings-Datei laden
          </Button>

          <input
            ref={decisionsInputRef}
            type="file"
            accept="application/json,.json"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0]
              // Zurücksetzen, damit dieselbe Datei erneut gewählt werden kann.
              event.target.value = ''
              if (file) decisionsFile.onImport(file)
            }}
          />
          <Button
            variant="outline"
            size="xs"
            onClick={() => decisionsInputRef.current?.click()}
          >
            <UploadIcon data-icon="inline-start" />
            Entscheidungen laden
          </Button>
          <Button
            variant="outline"
            size="xs"
            disabled={decisionsFile.count === 0}
            title={
              decisionsFile.count === 0
                ? 'Noch keine Entscheidung in dieser Sitzung'
                : undefined
            }
            onClick={decisionsFile.onExport}
          >
            <DownloadIcon data-icon="inline-start" />
            Entscheidungen sichern
            {decisionsFile.count > 0 && (
              <span className="font-mono tabular-nums"> ({decisionsFile.count})</span>
            )}
          </Button>
          <Button
            variant="outline"
            size="xs"
            disabled={decisionsFile.cleanupCount === 0}
            title={
              decisionsFile.cleanupCount === 0
                ? 'Noch keine übernommene Massenänderung in dieser Sitzung'
                : undefined
            }
            onClick={decisionsFile.onExportCleanup}
          >
            <DownloadIcon data-icon="inline-start" />
            Bereinigungsliste (CSV)
            {decisionsFile.cleanupCount > 0 && (
              <span className="font-mono tabular-nums"> ({decisionsFile.cleanupCount})</span>
            )}
          </Button>
        </div>
      </div>

      {loadError && (
        <p className="flex items-start gap-2 border-t border-destructive/30 bg-destructive/5 px-6 py-2 text-xs text-destructive">
          <AlertTriangleIcon className="mt-px size-3.5 shrink-0" />
          <span>Datei nicht geladen: {loadError}</span>
        </p>
      )}

      {decisionsFile.message && (
        <div
          className={
            decisionsFile.message.kind === 'error'
              ? 'flex items-start gap-2 border-t border-destructive/30 bg-destructive/5 px-6 py-2 text-xs text-destructive'
              : 'flex items-start gap-2 border-t bg-muted/40 px-6 py-2 text-xs text-muted-foreground'
          }
        >
          {decisionsFile.message.kind === 'error' ? (
            <AlertTriangleIcon className="mt-px size-3.5 shrink-0" />
          ) : (
            <InfoIcon className="mt-px size-3.5 shrink-0" />
          )}
          <span className="flex flex-col gap-0.5">
            {decisionsFile.message.lines.map((line) => (
              <span key={line}>{line}</span>
            ))}
          </span>
        </div>
      )}
    </div>
  )
}
