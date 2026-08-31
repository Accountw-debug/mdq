/**
 * Bereinigungsliste als CSV (Spec Sprint 5, Aufgabe 7) – reine Funktionen ohne DOM.
 *
 * Die Liste ist eine Arbeitsanweisung, keine Bestandsaufnahme: sie enthält genau
 * die Findings vom Aktionstyp Massenänderung, die übernommen wurden – einzeln oder
 * über eine Stichproben-Freigabe (Freigabe Victor, 2026-08-30). Wer nichts
 * entschieden hat, bekommt keine Zeile.
 *
 * Konventionen, damit die Datei in Excel ohne Nacharbeit aufgeht: Trenner `;`,
 * Zeilenende CRLF, UTF-8 **mit** BOM (ohne BOM zerlegt Excel die Umlaute).
 * Reihenfolge: Regel, dann Geschäftspartner, dann `finding_id` – gleicher Stand,
 * gleiche Datei (CLAUDE.md, Regel 9). Beträge kommen in den Spalten nicht vor;
 * `current`/`proposed` sind Feldwerte, die unverändert übernommen werden.
 */

import type { DecisionsState } from '@/state/decisions'
import type { Finding, RunInfo } from '@/types/finding'

/** Spalten in der Reihenfolge der Spec – der Kopf der Datei. */
export const CLEANUP_COLUMNS = [
  'bp_key',
  'company_code',
  'source_table',
  'source_field',
  'current',
  'proposed',
  'tier',
  'rule_id',
] as const

const SEPARATOR = ';'
const NEWLINE = '\r\n'
/** Byte Order Mark – ohne ihn liest Excel die Datei als Latin-1. */
const BOM = '﻿'

/** Übernommene Massenänderungen, deterministisch sortiert. */
export function cleanupFindings(
  findings: readonly Finding[],
  decisions: DecisionsState,
): Finding[] {
  return findings
    .filter(
      (finding) =>
        finding.action_type === 'mass_change' &&
        decisions[finding.finding_id]?.action === 'accept',
    )
    .sort((a, b) => {
      const byRule = compareText(a.rule_id, b.rule_id)
      if (byRule !== 0) return byRule
      const byPartner = compareText(a.entity.bp_key, b.entity.bp_key)
      return byPartner !== 0 ? byPartner : compareText(a.finding_id, b.finding_id)
    })
}

function compareText(a: string, b: string): number {
  if (a < b) return -1
  if (a > b) return 1
  return 0
}

/** Eine Zeile je Finding – leere Felder bleiben leer, kein „–" (Regel 4). */
export function cleanupRow(finding: Finding): string[] {
  return [
    finding.entity.bp_key,
    finding.entity.company_code ?? '',
    finding.current.source_table,
    finding.current.source_field,
    finding.current.value ?? '',
    finding.proposed?.value ?? '',
    finding.tier,
    finding.rule_id,
  ]
}

/**
 * Ein Feld nach RFC 4180: nur quoten, wenn es sein muss, inneres `"` verdoppeln.
 * Ein Wert mit Semikolon darf die Spalten nicht verschieben.
 */
function escapeField(value: string): string {
  if (!/[;"\r\n]/.test(value)) return value
  return `"${value.replaceAll('"', '""')}"`
}

export function toCsv(rows: readonly (readonly string[])[]): string {
  const lines = [
    [...CLEANUP_COLUMNS].join(SEPARATOR),
    ...rows.map((row) => row.map(escapeField).join(SEPARATOR)),
  ]
  return BOM + lines.join(NEWLINE) + NEWLINE
}

/** Die ganze Bereinigungsliste als Text, wie sie auf die Platte geht. */
export function buildCleanupCsv(
  findings: readonly Finding[],
  decisions: DecisionsState,
): string {
  return toCsv(cleanupFindings(findings, decisions).map(cleanupRow))
}

/** Dateiname – der Lauf steht darin, damit zwei Listen unterscheidbar sind. */
export function cleanupFileName(run: RunInfo): string {
  return `bereinigungsliste-${run.run_id}.csv`
}
