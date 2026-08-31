/**
 * Die eine Stelle, an der steht, woher das UI seine Findings nimmt.
 *
 * Kommt ein Backend, wird hier `buildSource()` gegen die neue Implementierung
 * getauscht – kein Screen und keine Ansicht merkt davon etwas.
 *
 * Bewusst **nicht** Teil von `FindingsSource`: eine Lauf-Auswahl (`listRuns`).
 * Sie ist ein eigener Vertrag (`FindingsCatalog`) und ein eigenes Feature; siehe
 * die Notiz in `ui/NOTES.md`.
 */

import { buildSource } from '@/sources/build-source'
import type { FindingsSource } from '@/sources/findings-source'

export { LoadError } from '@/sources/findings-source'
export type { FindingsSource, LoadedRun, SourceKind } from '@/sources/findings-source'
export { checkFindings, checkRun, deriveRun, parseFindings, parseRun } from '@/sources/parse'
export { buildSource } from '@/sources/build-source'
export { fileSource } from '@/sources/file-source'

/** Startquelle der Anwendung. */
export const DEFAULT_SOURCE: FindingsSource = buildSource()
