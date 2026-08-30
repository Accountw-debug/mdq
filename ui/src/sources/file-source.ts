/**
 * Findings aus einer Datei, die der Bearbeiter im Datenstand-Banner wählt –
 * damit lässt sich `runs/<run_id>/findings.json` der Engine ohne Rebuild ansehen.
 *
 * Die Datei wird nur im Speicher gehalten: kein localStorage, nichts bleibt
 * unbemerkt im Browser liegen (Spec Sprint 5).
 */

import { deriveRun, parseFindings } from '@/sources/parse'
import type { FindingsSource, LoadedRun } from '@/sources/findings-source'

export function fileSource(file: File): FindingsSource {
  return {
    kind: 'file',
    label: file.name,
    async loadRun(): Promise<LoadedRun> {
      const findings = parseFindings(await file.text())
      return { run: deriveRun(findings), findings }
    },
  }
}
