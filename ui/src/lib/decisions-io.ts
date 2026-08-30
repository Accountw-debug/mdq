/**
 * Schreiben und Lesen von `decisions.json` – reine Funktionen, ohne DOM.
 *
 * Der Vertrag steht in `@/types/decisions-file`. Hier steht, wie er eingehalten
 * wird: die Ausgabe ist deterministisch (nach `finding_id` sortiert, CLAUDE.md
 * Regel 9), und beim Lesen wird nichts stumm verworfen (Regel 4) – was nicht
 * angewandt werden kann, steht im Bericht. Meldungen nennen nur `finding_id` und
 * Feldnamen, nie Geschäftspartnerdaten (Regel 8).
 */

import { LoadError } from '@/sources/findings-source'
import { formatDateTime } from '@/lib/format'
import type { DecisionsState } from '@/state/decisions'
import { DECISION_ACTIONS, REASON_CODES } from '@/types/decision'
import type { DecisionAction, DecisionRecord, ReasonCode } from '@/types/decision'
import { DECISIONS_FORMAT, DECISIONS_FORMAT_VERSION } from '@/types/decisions-file'
import type { DecisionsFile } from '@/types/decisions-file'
import type { Finding, RunInfo } from '@/types/finding'

/** Felder, die der Umschlag kennt – alles andere kommt in den Bericht. */
const ENVELOPE_FIELDS = new Set<string>([
  'format',
  'format_version',
  'run_id',
  'data_as_of',
  'engine_version',
  'pack_version',
  'exported_at',
  'exported_by',
  'decisions',
])

/** Felder, die ein Entscheidungssatz kennt. */
const RECORD_FIELDS = new Set<string>([
  'finding_id',
  'action',
  'reason_code',
  'reason',
  'assigned_to',
  'by',
  'at',
])

/** Dateiname des Exports – der Lauf steht darin, damit zwei Dateien unterscheidbar sind. */
export function decisionsFileName(run: RunInfo): string {
  return `decisions-${run.run_id}.json`
}

/**
 * Baut die Datei. Die Uhr kommt von außen wie bei `createDecision`: `exported_at`
 * ist der einzige Wert, der nicht aus den Daten folgt (Regel 9).
 */
export function buildDecisionsFile(
  run: RunInfo,
  decisions: DecisionsState,
  exportedBy: string,
  now: () => string = () => new Date().toISOString(),
): DecisionsFile {
  return {
    format: DECISIONS_FORMAT,
    format_version: DECISIONS_FORMAT_VERSION,
    run_id: run.run_id,
    data_as_of: run.data_as_of,
    engine_version: run.engine_version,
    pack_version: run.pack_version,
    exported_at: now(),
    exported_by: exportedBy.trim(),
    // Sortiert: gleicher Stand, gleiche Datei – bis aufs Byte.
    decisions: Object.values(decisions).sort((a, b) =>
      a.finding_id < b.finding_id ? -1 : a.finding_id > b.finding_id ? 1 : 0,
    ),
  }
}

/** Die Datei als Text, wie sie auf die Platte geht. */
export function serializeDecisionsFile(file: DecisionsFile): string {
  return `${JSON.stringify(file, null, 2)}\n`
}

/**
 * Was der Import getan hat. Steht so im Banner – und beantwortet die Frage, die
 * beim Wiederaufnehmen zuerst kommt: passt die Datei zu dem, was auf dem Schirm ist?
 */
export interface ImportReport {
  /** Sätze in der Datei. */
  total: number
  /** Davon mit einem Finding im geladenen Lauf – nur diese werden angewandt. */
  applied: number
  /** `finding_id`s ohne Finding im geladenen Lauf. */
  missing: string[]
  /** Gesetzt, wenn die Datei zu einem anderen Lauf gehört als der geladene. */
  runMismatch: { file: string; loaded: string } | null
  /** Felder, die dieser Leser nicht kennt – gelesen wurden sie nicht. */
  unknownFields: string[]
  exportedBy: string
  exportedAt: string
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function requireString(value: unknown, where: string, field: string): string {
  const found = isRecord(value) ? value[field] : undefined
  if (typeof found !== 'string' || found.trim() === '') {
    throw new LoadError(`${where}: Pflichtfeld fehlt oder ist leer: ${field}`)
  }
  return found
}

function checkRecord(
  value: unknown,
  index: number,
  unknownFields: Set<string>,
): DecisionRecord {
  const at = `Entscheidung ${index + 1}`
  if (!isRecord(value)) throw new LoadError(`${at}: kein Objekt`)

  const findingId = requireString(value, at, 'finding_id')
  const where = findingId

  for (const key of Object.keys(value)) {
    if (!RECORD_FIELDS.has(key)) unknownFields.add(`decisions[].${key}`)
  }

  const action = requireString(value, where, 'action')
  if (!DECISION_ACTIONS.includes(action as DecisionAction)) {
    throw new LoadError(`${where}: unbekannte Aktion: ${action}`)
  }

  const reasonCode = value.reason_code
  if (reasonCode != null && !REASON_CODES.includes(reasonCode as ReasonCode)) {
    throw new LoadError(`${where}: unbekannter reason_code: ${String(reasonCode)}`)
  }

  const timestamp = requireString(value, where, 'at')
  try {
    formatDateTime(timestamp)
  } catch {
    throw new LoadError(`${where}: at ist kein UTC-Zeitstempel (erwartet …Z)`)
  }

  const assignedTo = value.assigned_to
  if (assignedTo != null && typeof assignedTo !== 'string') {
    throw new LoadError(`${where}: assigned_to ist kein Text`)
  }

  return {
    finding_id: findingId,
    action: action as DecisionAction,
    reason_code: (reasonCode ?? null) as ReasonCode | null,
    reason: requireString(value, where, 'reason'),
    assigned_to: (assignedTo ?? null) as string | null,
    by: requireString(value, where, 'by'),
    at: timestamp,
  }
}

/**
 * Liest eine Entscheidungsdatei gegen den geladenen Lauf.
 *
 * Abbruch (`LoadError`) nur, wenn die Datei als Ganzes nicht taugt: falsches
 * Format, unbekannte Version, kaputter Satz. Dass die Datei zu einem **anderen**
 * Lauf gehört, ist dagegen kein Abbruch, sondern eine Warnung im Bericht –
 * `finding_id` ist deterministisch, ein Finding kann denselben Schlüssel im
 * nächsten Lauf tragen (Freigabe Victor, 2026-08-30).
 */
export function parseDecisionsFile(
  text: string,
  run: RunInfo,
  findings: readonly Finding[],
): { records: DecisionsState; report: ImportReport } {
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch (error) {
    throw new LoadError(`Datei ist kein gültiges JSON: ${(error as Error).message}`)
  }
  if (!isRecord(parsed)) throw new LoadError('Erwartet wird ein Objekt mit "decisions"')

  if (parsed.format !== DECISIONS_FORMAT) {
    throw new LoadError(
      `Keine Entscheidungsdatei: format ist ${JSON.stringify(parsed.format ?? null)}, erwartet "${DECISIONS_FORMAT}"`,
    )
  }
  if (parsed.format_version !== DECISIONS_FORMAT_VERSION) {
    throw new LoadError(
      `Unbekannte format_version: ${String(parsed.format_version)}. Dieses UI liest Version ${DECISIONS_FORMAT_VERSION}.`,
    )
  }
  if (!Array.isArray(parsed.decisions)) {
    throw new LoadError('Pflichtfeld fehlt oder ist keine Liste: decisions')
  }

  const unknownFields = new Set<string>()
  for (const key of Object.keys(parsed)) {
    if (!ENVELOPE_FIELDS.has(key)) unknownFields.add(key)
  }

  const parsedRecords = parsed.decisions.map((entry, index) =>
    checkRecord(entry, index, unknownFields),
  )

  const seen = new Set<string>()
  for (const record of parsedRecords) {
    if (seen.has(record.finding_id)) {
      throw new LoadError(`finding_id kommt doppelt vor: ${record.finding_id}`)
    }
    seen.add(record.finding_id)
  }

  const known = new Set(findings.map((finding) => finding.finding_id))
  const records: Record<string, DecisionRecord> = {}
  const missing: string[] = []
  for (const record of parsedRecords) {
    if (known.has(record.finding_id)) records[record.finding_id] = record
    else missing.push(record.finding_id)
  }

  const fileRunId = typeof parsed.run_id === 'string' ? parsed.run_id : ''
  return {
    records,
    report: {
      total: parsedRecords.length,
      applied: Object.keys(records).length,
      missing,
      runMismatch: fileRunId === run.run_id ? null : { file: fileRunId, loaded: run.run_id },
      unknownFields: [...unknownFields].sort(),
      exportedBy: typeof parsed.exported_by === 'string' ? parsed.exported_by : '',
      exportedAt: typeof parsed.exported_at === 'string' ? parsed.exported_at : '',
    },
  }
}

/**
 * Der Bericht in Sätzen – hier und nicht in der Komponente, damit der Wortlaut
 * im Test steht. Die erste Zeile sagt immer, wie viele Entscheidungen ein Finding
 * im geladenen Lauf gefunden haben und wie viele nicht.
 */
export function describeImport(report: ImportReport): string[] {
  const lines: string[] = []
  lines.push(
    `${report.applied} von ${report.total} Entscheidungen übernommen; ` +
      `${report.missing.length} ohne Finding im geladenen Lauf.`,
  )
  if (report.missing.length > 0) {
    lines.push(`Ohne Finding: ${report.missing.join(', ')}`)
  }
  if (report.runMismatch != null) {
    lines.push(
      `Die Datei gehört zu Lauf ${report.runMismatch.file || '(ohne run_id)'}, ` +
        `geladen ist ${report.runMismatch.loaded}.`,
    )
  }
  if (report.unknownFields.length > 0) {
    lines.push(`Nicht gelesene Felder: ${report.unknownFields.join(', ')}`)
  }
  return lines
}
