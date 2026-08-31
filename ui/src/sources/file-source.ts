/**
 * Findings aus Dateien, die der Bearbeiter im Datenstand-Banner wählt – damit lässt
 * sich `runs/<run_id>/` der Engine ohne Rebuild ansehen.
 *
 * Gewählt werden `findings.json` und, wenn vorhanden, `run.json` desselben Laufs.
 * Erst mit `run.json` stimmt der Datenstand: `tables_loaded` und die Buchungskreise
 * beschreiben den **Lauf**, nicht die Findings – ein Buchungskreis ohne Befund
 * verschwände sonst aus dem Banner. Ohne `run.json` bleibt es beim Notbehelf
 * `deriveRun` mit `tables_loaded: 0`.
 *
 * Unterschieden werden die Dateien an ihrem Inhalt, nicht am Namen: eine Liste (oder
 * ein Objekt mit `findings`) sind die Findings, ein Objekt mit `run_id` ist der
 * Lauf-Kopf. Wer die Dateien umbenennt, bekommt trotzdem das Richtige.
 *
 * Die Dateien werden nur im Speicher gehalten: kein localStorage, nichts bleibt
 * unbemerkt im Browser liegen (Spec Sprint 5).
 */

import { checkFindings, checkRun, deriveRun } from '@/sources/parse'
import { LoadError, type FindingsSource, type LoadedRun } from '@/sources/findings-source'

interface ReadFile {
  name: string
  parsed: unknown
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Sieht die Datei wie eine Findings-Liste aus? */
function looksLikeFindings(parsed: unknown): boolean {
  return Array.isArray(parsed) || (isRecord(parsed) && Array.isArray(parsed.findings))
}

/** Sieht die Datei wie ein Lauf-Kopf aus? */
function looksLikeRun(parsed: unknown): boolean {
  return isRecord(parsed) && parsed.run_id != null && !looksLikeFindings(parsed)
}

async function readJson(file: File): Promise<ReadFile> {
  const text = await file.text()
  try {
    return { name: file.name, parsed: JSON.parse(text) }
  } catch (error) {
    throw new LoadError(`${file.name} ist kein gültiges JSON: ${(error as Error).message}`)
  }
}

export function fileSource(files: readonly File[]): FindingsSource {
  if (files.length === 0) throw new LoadError('Keine Datei gewählt')
  const label = files.map((file) => file.name).join(' + ')

  return {
    kind: 'file',
    label,
    async loadRun(): Promise<LoadedRun> {
      const read = await Promise.all(files.map(readJson))

      const findingsFiles = read.filter((entry) => looksLikeFindings(entry.parsed))
      const runFiles = read.filter((entry) => looksLikeRun(entry.parsed))
      const unknownFiles = read.filter(
        (entry) => !looksLikeFindings(entry.parsed) && !looksLikeRun(entry.parsed),
      )

      // Nichts wird stumm übergangen (CLAUDE.md, Regel 4).
      if (unknownFiles.length > 0) {
        throw new LoadError(
          `Weder Findings noch Lauf-Kopf: ${unknownFiles.map((entry) => entry.name).join(', ')}`,
        )
      }
      if (findingsFiles.length === 0) {
        throw new LoadError('Es fehlt die Findings-Datei – run.json allein reicht nicht')
      }
      if (findingsFiles.length > 1) {
        throw new LoadError(
          `Mehr als eine Findings-Datei gewählt: ${findingsFiles.map((entry) => entry.name).join(', ')}`,
        )
      }
      if (runFiles.length > 1) {
        throw new LoadError(
          `Mehr als eine run.json gewählt: ${runFiles.map((entry) => entry.name).join(', ')}`,
        )
      }

      const findings = checkFindings(findingsFiles[0].parsed)
      const run = runFiles.length === 1 ? checkRun(runFiles[0].parsed, findings) : deriveRun(findings)
      return { run, findings }
    },
  }
}
