/**
 * Prüfen und Ableiten – rein, ohne Netz und ohne DOM.
 *
 * Jede `FindingsSource` führt ihre Daten hier hindurch: die Datei aus dem Banner
 * genauso wie später die Antwort einer API. Damit gelten für jede Quelle dieselben
 * Prüfungen und dieselben Meldungen.
 *
 * Fehler werden nie geschluckt (CLAUDE.md, Regel 4): jede unbrauchbare Datei führt
 * zu einer Meldung mit Position und Feldname. Die Meldungen nennen nur Schlüssel,
 * Regel-IDs und Feldnamen, keine Geschäftspartnerdaten (Regel 8).
 */

import { LoadError } from '@/sources/findings-source'
import type { Finding, RunInfo } from '@/types/finding'
import { ACTION_TYPES } from '@/types/finding'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * Prüft die Felder, ohne die der Explorer nicht arbeiten kann. Das ist keine
 * Schema-Validierung – die gehört in die Engine (`uv run mdq validate`); hier geht
 * es nur darum, dass eine falsche Datei sofort auffällt statt halb zu erscheinen.
 */
function checkFinding(index: number, value: unknown): Finding {
  const at = `Finding ${index + 1}`
  if (!isRecord(value)) throw new LoadError(`${at}: kein Objekt`)
  // `title` steht seit dem Schema-Stand von D-069 unter `required`; die Findings-Liste
  // hat eine Spalte dafür. Fehlt er, ist das eine ungültige Datei und keine leere Zelle.
  for (const field of [
    'finding_id',
    'run_id',
    'rule_id',
    'action_type',
    'status',
    'data_as_of',
    'title',
  ]) {
    if (value[field] == null) throw new LoadError(`${at}: Pflichtfeld fehlt: ${field}`)
  }
  const findingId = String(value.finding_id)
  if (!isRecord(value.entity) || value.entity.bp_key == null) {
    throw new LoadError(`${findingId}: Pflichtfeld fehlt: entity.bp_key`)
  }
  if (!isRecord(value.current)) throw new LoadError(`${findingId}: Pflichtfeld fehlt: current`)
  if (!ACTION_TYPES.includes(value.action_type as (typeof ACTION_TYPES)[number])) {
    throw new LoadError(`${findingId}: unbekannter Aktionstyp: ${String(value.action_type)}`)
  }
  return value as unknown as Finding
}

/**
 * Prüft eine bereits geparste Findings-Liste: entweder ein Array oder
 * `{ findings: [...] }`. Einstiegspunkt für Quellen, die schon JSON in der Hand
 * haben (`fetch` → `response.json()`).
 */
export function checkFindings(parsed: unknown): Finding[] {
  const list = Array.isArray(parsed)
    ? parsed
    : isRecord(parsed) && Array.isArray(parsed.findings)
      ? parsed.findings
      : null
  if (list === null) {
    throw new LoadError('Erwartet wird ein Array von Findings oder ein Objekt mit "findings"')
  }
  if (list.length === 0) throw new LoadError('Die Datei enthält keine Findings')
  const findings = list.map((entry, index) => checkFinding(index, entry))

  const seen = new Set<string>()
  for (const finding of findings) {
    if (seen.has(finding.finding_id)) {
      throw new LoadError(`finding_id kommt doppelt vor: ${finding.finding_id}`)
    }
    seen.add(finding.finding_id)
  }
  return findings
}

/** Liest ein Findings-JSON aus Text. */
export function parseFindings(text: string): Finding[] {
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch (error) {
    throw new LoadError(`Datei ist kein gültiges JSON: ${(error as Error).message}`)
  }
  return checkFindings(parsed)
}

/** Genau ein Wert über alle Findings – sonst gehören sie nicht zu einem Lauf. */
function singleValue<K extends 'run_id' | 'data_as_of' | 'engine_version' | 'pack_version'>(
  findings: readonly Finding[],
  field: K,
): string {
  const values = [...new Set(findings.map((finding) => finding[field]))]
  if (values.length !== 1) {
    throw new LoadError(`Uneinheitliches Feld ${field} über die Findings: ${values.join(' | ')}`)
  }
  return values[0]
}

/**
 * Lauf-Kopf aus einer `run.json` der Engine. Gelesen werden nur die Felder von
 * `RunInfo`; alles Weitere in der Datei (Dateiliste, Regelbilanz, Rejects, Scope)
 * bleibt unberührt – der Lauf-Bericht ist reicher als das Banner.
 *
 * Die Findings sind der Gegenschlüssel: passt `run_id` nicht, gehören die beiden
 * Dateien zu verschiedenen Läufen, und das wird gemeldet statt stumm gemischt
 * (CLAUDE.md, Regel 4).
 */
export function checkRun(parsed: unknown, findings: readonly Finding[]): RunInfo {
  if (!isRecord(parsed)) throw new LoadError('run.json: kein Objekt')
  for (const field of ['run_id', 'data_as_of', 'engine_version', 'pack_version']) {
    if (parsed[field] == null) throw new LoadError(`run.json: Pflichtfeld fehlt: ${field}`)
  }
  const runId = String(parsed.run_id)
  const findingsRunId = singleValue(findings, 'run_id')
  if (runId !== findingsRunId) {
    throw new LoadError(
      `run.json gehört zu einem anderen Lauf: ${runId} statt ${findingsRunId}`,
    )
  }
  const tablesLoaded = parsed.tables_loaded
  if (tablesLoaded != null && typeof tablesLoaded !== 'number') {
    throw new LoadError('run.json: tables_loaded ist keine Zahl')
  }
  const companyCodes = parsed.company_codes
  if (companyCodes != null && !Array.isArray(companyCodes)) {
    throw new LoadError('run.json: company_codes ist keine Liste')
  }
  return {
    run_id: runId,
    data_as_of: String(parsed.data_as_of),
    engine_version: String(parsed.engine_version),
    pack_version: String(parsed.pack_version),
    tables_loaded: tablesLoaded ?? 0,
    // Die Buchungskreise des Laufs, nicht die der Findings: ein Buchungskreis ohne
    // Befund gehört trotzdem in den Datenstand.
    company_codes: (companyCodes ?? []).map(String),
  }
}

/** Liest eine `run.json` aus Text. */
export function parseRun(text: string, findings: readonly Finding[]): RunInfo {
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch (error) {
    throw new LoadError(`run.json ist kein gültiges JSON: ${(error as Error).message}`)
  }
  return checkRun(parsed, findings)
}

/**
 * Notbehelf, solange nur `findings.json` vorliegt: der Lauf-Kopf wird aus den
 * Findings abgeleitet, gleiche Ableitung wie in `scripts/build-data.mjs`.
 * `tables_loaded` bleibt 0 – die echte Zahl steht in `runs/<run_id>/run.json`,
 * und die Buchungskreise sind hier nur die der Findings, nicht die des Laufs.
 */
export function deriveRun(findings: readonly Finding[]): RunInfo {
  const companyCodes = [
    ...new Set(
      findings
        .map((finding) => finding.entity.company_code)
        .filter((code): code is string => code != null),
    ),
  ].sort()
  return {
    run_id: singleValue(findings, 'run_id'),
    data_as_of: singleValue(findings, 'data_as_of'),
    engine_version: singleValue(findings, 'engine_version'),
    pack_version: singleValue(findings, 'pack_version'),
    tables_loaded: 0,
    company_codes: companyCodes,
  }
}
