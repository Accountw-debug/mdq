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
import type { SamplesState } from '@/state/samples'
import {
  DECISIONS_FORMAT,
  DECISIONS_FORMAT_VERSION,
  SAMPLE_OUTCOMES,
} from '@/types/decisions-file'
import type { DecisionsFile, SampleReview } from '@/types/decisions-file'
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
  'sample_reviewed',
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

/** Felder, die ein Stichproben-Satz kennt. */
const SAMPLE_FIELDS = new Set<string>([
  'rule_id',
  'outcome',
  'sampled_finding_ids',
  'applied_finding_ids',
  'blocked_by_finding_id',
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
  samples: SamplesState,
  exportedBy: string,
  now: () => string = () => new Date().toISOString(),
): DecisionsFile {
  const reviews = Object.values(samples).sort((a, b) =>
    a.rule_id < b.rule_id ? -1 : a.rule_id > b.rule_id ? 1 : 0,
  )
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
    // Das Feld erscheint erst, wenn es etwas zu berichten gibt – eine leere Liste
    // in jeder Datei wäre nur Rauschen für den Leser.
    ...(reviews.length === 0 ? {} : { sample_reviewed: reviews }),
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
  /** Stichproben-Sätze in der Datei (`sample_reviewed`). */
  samplesTotal: number
  /** Davon mit einer Regel im geladenen Lauf – nur diese werden angewandt. */
  samplesApplied: number
  /** `rule_id`s ohne Finding im geladenen Lauf. */
  missingSampleRules: string[]
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

/** Liste von Texten, sonst Abbruch – eine halb gelesene Stichprobe wäre wertlos. */
function requireStringList(
  value: Record<string, unknown>,
  where: string,
  field: string,
): string[] {
  const found = value[field]
  if (!Array.isArray(found) || found.some((entry) => typeof entry !== 'string')) {
    throw new LoadError(`${where}: ${field} ist keine Liste von finding_ids`)
  }
  return found as string[]
}

/**
 * Prüft einen Stichproben-Satz. Er kam additiv dazu (Aufgabe 7) und ändert die
 * Version nicht – ein älterer Leser nennt ihn als unbekanntes Feld und liest die
 * Entscheidungen weiter.
 */
function checkSample(
  value: unknown,
  index: number,
  unknownFields: Set<string>,
): SampleReview {
  const at = `Stichprobe ${index + 1}`
  if (!isRecord(value)) throw new LoadError(`${at}: kein Objekt`)

  const ruleId = requireString(value, at, 'rule_id')
  const where = ruleId

  for (const key of Object.keys(value)) {
    if (!SAMPLE_FIELDS.has(key)) unknownFields.add(`sample_reviewed[].${key}`)
  }

  const outcome = requireString(value, where, 'outcome')
  if (!SAMPLE_OUTCOMES.includes(outcome as SampleReview['outcome'])) {
    throw new LoadError(`${where}: unbekannter outcome: ${outcome}`)
  }

  const timestamp = requireString(value, where, 'at')
  try {
    formatDateTime(timestamp)
  } catch {
    throw new LoadError(`${where}: at ist kein UTC-Zeitstempel (erwartet …Z)`)
  }

  const blockedBy = value.blocked_by_finding_id
  if (blockedBy != null && typeof blockedBy !== 'string') {
    throw new LoadError(`${where}: blocked_by_finding_id ist kein Text`)
  }

  return {
    rule_id: ruleId,
    outcome: outcome as SampleReview['outcome'],
    sampled_finding_ids: requireStringList(value, where, 'sampled_finding_ids'),
    applied_finding_ids: requireStringList(value, where, 'applied_finding_ids'),
    blocked_by_finding_id: (blockedBy ?? null) as string | null,
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
): { records: DecisionsState; samples: SamplesState; report: ImportReport } {
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
  // Das Feld ist optional; steht es da, muss es eine Liste sein.
  if (parsed.sample_reviewed != null && !Array.isArray(parsed.sample_reviewed)) {
    throw new LoadError('sample_reviewed ist keine Liste')
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

  const parsedSamples = (parsed.sample_reviewed ?? []).map(
    (entry: unknown, index: number) => checkSample(entry, index, unknownFields),
  )
  const seenRules = new Set<string>()
  for (const review of parsedSamples) {
    if (seenRules.has(review.rule_id)) {
      throw new LoadError(`rule_id kommt in sample_reviewed doppelt vor: ${review.rule_id}`)
    }
    seenRules.add(review.rule_id)
  }

  // Eine Stichprobe gehört zu einer Regel des Laufs; kennt der Lauf die Regel
  // nicht, wird der Satz nicht angewandt – aber genannt (Regel 4).
  const knownRules = new Set(findings.map((finding) => finding.rule_id))
  const samples: Record<string, SampleReview> = {}
  const missingSampleRules: string[] = []
  for (const review of parsedSamples) {
    if (knownRules.has(review.rule_id)) samples[review.rule_id] = review
    else missingSampleRules.push(review.rule_id)
  }

  const fileRunId = typeof parsed.run_id === 'string' ? parsed.run_id : ''
  return {
    records,
    samples,
    report: {
      total: parsedRecords.length,
      applied: Object.keys(records).length,
      missing,
      runMismatch: fileRunId === run.run_id ? null : { file: fileRunId, loaded: run.run_id },
      unknownFields: [...unknownFields].sort(),
      samplesTotal: parsedSamples.length,
      samplesApplied: Object.keys(samples).length,
      missingSampleRules,
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
  if (report.samplesTotal > 0) {
    lines.push(
      `${report.samplesApplied} von ${report.samplesTotal} geprüften Stichproben übernommen.`,
    )
  }
  if (report.missingSampleRules.length > 0) {
    lines.push(`Ohne Regel im geladenen Lauf: ${report.missingSampleRules.join(', ')}`)
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
