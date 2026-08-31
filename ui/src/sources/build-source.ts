/**
 * Findings aus `public/data/`, wie `scripts/build-data.mjs` sie aus
 * `logic/examples/findings/*.yaml` erzeugt. Die Quelle des Prototyps – sie bleibt,
 * solange kein Lauf-Verzeichnis der Engine vorliegt.
 */

import { checkFindings } from '@/sources/parse'
import { LoadError, type FindingsSource, type LoadedRun } from '@/sources/findings-source'
import type { RunInfo } from '@/types/finding'

async function fetchJson(url: string, signal?: AbortSignal): Promise<unknown> {
  let response: Response
  try {
    response = await fetch(url, { signal })
  } catch (error) {
    // Abbrüche gehören dem Aufrufer und bleiben, was sie sind.
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new LoadError(`${url} nicht erreichbar: ${(error as Error).message}`)
  }
  if (!response.ok) throw new LoadError(`${url}: HTTP ${response.status}`)
  try {
    return await response.json()
  } catch (error) {
    throw new LoadError(`${url} ist kein gültiges JSON: ${(error as Error).message}`)
  }
}

export function buildSource(): FindingsSource {
  return {
    kind: 'build',
    label: 'Beispiel-Findings',
    async loadRun(signal?: AbortSignal): Promise<LoadedRun> {
      const [run, findings] = await Promise.all([
        fetchJson('data/run.json', signal),
        fetchJson('data/findings.json', signal),
      ])
      // Der Lauf-Kopf kommt hier aus einer eigenen Datei; ab Sprint 3 ist das
      // `runs/<run_id>/run.json` der Engine, dann mit echtem `tables_loaded`.
      return { run: run as RunInfo, findings: checkFindings(findings) }
    },
  }
}
