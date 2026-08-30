/**
 * Laden der Findings – aus `public/data/` beim Start oder aus einer Datei, die der
 * Nutzer im Datenstand-Banner auswählt (später `runs/<run_id>/findings.json` der Engine).
 *
 * Fehler werden nie geschluckt (CLAUDE.md, Regel 4): jede unbrauchbare Datei führt
 * zu einer Meldung mit Position und Feldname. Die Meldungen nennen nur Schlüssel,
 * Regel-IDs und Feldnamen, keine Geschäftspartnerdaten (Regel 8).
 */

import type { Finding, RunInfo } from '@/types/finding'
import { ACTION_TYPES } from '@/types/finding'

export interface LoadedRun {
  run: RunInfo
  findings: Finding[]
  /** Woher die Daten stammen – für den Hinweis im Banner. */
  source: { kind: 'build'; label: string } | { kind: 'file'; label: string }
}

export class LoadError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'LoadError'
  }
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) throw new LoadError(`${url}: HTTP ${response.status}`)
  return (await response.json()) as T
}

/** Findings und Lauf-Kopf, wie `scripts/build-data.mjs` sie erzeugt. */
export async function loadRunFromBuild(): Promise<LoadedRun> {
  const [run, findings] = await Promise.all([
    fetchJson<RunInfo>('data/run.json'),
    fetchJson<Finding[]>('data/findings.json'),
  ])
  return { run, findings, source: { kind: 'build', label: 'Beispiel-Findings' } }
}

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
  for (const field of ['finding_id', 'run_id', 'rule_id', 'action_type', 'status', 'data_as_of']) {
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

/** Liest ein Findings-JSON: entweder ein Array oder `{ findings: [...] }`. */
export function parseFindings(text: string): Finding[] {
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch (error) {
    throw new LoadError(`Datei ist kein gültiges JSON: ${(error as Error).message}`)
  }
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
 * Lauf-Kopf aus den Findings, gleiche Ableitung wie in `scripts/build-data.mjs`.
 * `tables_loaded` bleibt 0 – die echte Zahl steht in `runs/<run_id>/run.json` der Engine.
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

/** „Findings-Datei laden" aus dem Banner. */
export async function loadRunFromFile(file: File): Promise<LoadedRun> {
  const findings = parseFindings(await file.text())
  return { run: deriveRun(findings), findings, source: { kind: 'file', label: file.name } }
}
