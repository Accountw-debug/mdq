import { useRef } from 'react'
import { AlertTriangleIcon, UploadIcon } from 'lucide-react'
import { Key } from '@/components/Key'
import { Button } from '@/components/ui/button'
import { formatDate } from '@/lib/format'
import type { LoadedRun } from '@/lib/load-run'

/**
 * Datenstand-Banner, auf jedem Screen oben (docs/CONCEPT.md, Abschnitt 9):
 * „Stand 28.08.2026 · Lauf demo-2026-08-30 · Engine 0.1.0 · Regelpaket 0.1".
 *
 * Rechts „Findings-Datei laden": damit lässt sich `runs/<run_id>/findings.json`
 * der Engine ohne Rebuild ansehen. Die Datei wird nur im Speicher gehalten –
 * kein localStorage, nichts bleibt unbemerkt im Browser liegen (Spec Sprint 5).
 */
export function DataBanner({
  run,
  source,
  onSelectFile,
  loadError,
}: {
  run: LoadedRun['run']
  source: LoadedRun['source']
  onSelectFile: (file: File) => void
  loadError: string | null
}) {
  const inputRef = useRef<HTMLInputElement>(null)

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
          <span className="hidden sm:inline">
            Quelle: {source.kind === 'file' ? <Key>{source.label}</Key> : source.label}
          </span>
          <input
            ref={inputRef}
            type="file"
            accept="application/json,.json"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0]
              // Zurücksetzen, damit dieselbe Datei erneut gewählt werden kann.
              event.target.value = ''
              if (file) onSelectFile(file)
            }}
          />
          <Button variant="outline" size="xs" onClick={() => inputRef.current?.click()}>
            <UploadIcon data-icon="inline-start" />
            Findings-Datei laden
          </Button>
        </div>
      </div>

      {loadError && (
        <p className="flex items-start gap-2 border-t border-destructive/30 bg-destructive/5 px-6 py-2 text-xs text-destructive">
          <AlertTriangleIcon className="mt-px size-3.5 shrink-0" />
          <span>Datei nicht geladen: {loadError}</span>
        </p>
      )}
    </div>
  )
}
