/**
 * Logik der Review-Karte – reine Funktionen, ohne React und ohne DOM.
 *
 * Hier liegt alles, was eine Entscheidung ausmacht: welche Aktion erlaubt ist,
 * welchen Status sie setzt, wie der Datensatz für den Export aussieht und in
 * welcher Reihenfolge die Evidenz erscheint. Die Komponenten zeichnen nur noch.
 */

import { DECISION_STATUS_LABELS, REASON_CODE_LABELS, STATUS_LABELS } from '@/lib/labels'
import type { DecisionAction, DecisionRecord, ReasonCode } from '@/types/decision'
import type { Evidence, Finding, FindingStatus } from '@/types/finding'

/** Tooltip am gesperrten Knopf „Übernehmen" (Spec Sprint 5, Aufgabe 3). */
export const ACCEPT_BLOCKED_DAMAGE_CLASS_1 =
  'Bankdaten: Vier-Augen erforderlich – nur Review'

export const ACCEPT_BLOCKED_NO_OPTION = 'Erst eine der Optionen wählen'

/**
 * Warum „Übernehmen" gesperrt ist – oder `null`, wenn es erlaubt ist.
 *
 * Schadensklasse 1 ist nie übernehmbar (CLAUDE.md, Regel 11: nie Stufe A, nie
 * automatisch). Liegen Optionen vor, ist erst zu wählen, was übernommen wird.
 */
export function acceptBlockedReason(
  finding: Finding,
  chosenOption: string | null = null,
): string | null {
  if (finding.damage_class === 1) return ACCEPT_BLOCKED_DAMAGE_CLASS_1
  const options = finding.proposed?.options ?? []
  if (options.length > 0 && chosenOption == null) return ACCEPT_BLOCKED_NO_OPTION
  return null
}

/**
 * Status nach einer Entscheidung (Freigabe Victor, 2026-08-30):
 * Übernehmen und Zuweisen setzen `in_progress` – entschieden ist nicht umgesetzt.
 * `done` vergibt erst der nächste Lauf, in dem das Finding nicht mehr auftaucht.
 * Ablehnen setzt `rejected`, mit Grund „Risiko akzeptiert" dagegen `accepted_risk`.
 */
export function statusForDecision(record: DecisionRecord): FindingStatus {
  switch (record.action) {
    case 'accept':
    case 'assign':
      return 'in_progress'
    case 'reject':
      return record.reason_code === 'accepted_risk' ? 'accepted_risk' : 'rejected'
  }
}

/** Statustext einer Entscheidung – „freigegeben" und „zugewiesen" sind beide `in_progress`. */
export function decisionStatusLabel(record: DecisionRecord): string {
  if (record.action === 'reject') return STATUS_LABELS[statusForDecision(record)]
  return DECISION_STATUS_LABELS[record.action]
}

export interface DecisionInput {
  findingId: string
  action: DecisionAction
  by: string
  /** Pflicht beim Ablehnen. */
  reasonCode?: ReasonCode | null
  /** Freitext; leer heißt: abgeleiteter Grund. */
  reason?: string
  /** Nur bei `assign`. */
  assignedTo?: string | null
  /** Nur bei `accept` mit Optionen: die gewählte Option. */
  chosenOption?: string | null
}

/** Grund, wenn der Bearbeiter keinen Freitext geschrieben hat. `reason` ist Pflicht im Schema. */
function derivedReason(input: DecisionInput): string {
  switch (input.action) {
    case 'accept':
      return input.chosenOption == null
        ? 'Vorschlag übernommen'
        : `Option gewählt: ${input.chosenOption}`
    case 'assign':
      return `Zugewiesen an ${input.assignedTo?.trim() || 'unbekannt'}`
    case 'reject':
      return input.reasonCode == null ? 'Abgelehnt' : REASON_CODE_LABELS[input.reasonCode]
  }
}

/**
 * Baut den Entscheidungssatz. Die Uhr kommt von außen: `at` ist der einzige Wert
 * im UI, der nicht aus den Daten folgt – im Test wird er festgehalten (Regel 9).
 */
export function createDecision(
  input: DecisionInput,
  now: () => string = () => new Date().toISOString(),
): DecisionRecord {
  const reason = input.reason?.trim()
  return {
    finding_id: input.findingId,
    action: input.action,
    reason_code: input.reasonCode ?? null,
    reason: reason == null || reason === '' ? derivedReason(input) : reason,
    assigned_to: input.action === 'assign' ? (input.assignedTo?.trim() ?? null) : null,
    by: input.by.trim(),
    at: now(),
  }
}

/**
 * Evidenz für das Panel: Widersprüche (`agrees: false`) zuerst, sonst bleibt die
 * Reihenfolge der Engine erhalten – gleiche Datei, gleiche Karte (Regel 9).
 */
export function sortEvidence(evidence: readonly Evidence[]): Evidence[] {
  return evidence
    .map((entry, index) => ({ entry, index }))
    .sort((a, b) => {
      const byAgreement = Number(a.entry.agrees) - Number(b.entry.agrees)
      return byAgreement !== 0 ? byAgreement : a.index - b.index
    })
    .map(({ entry }) => entry)
}

/**
 * Hat das Finding überhaupt Relevanzangaben? Leere Abschnitte werden ausgeblendet.
 *
 * `currency` allein zählt nicht: die Währung ist im Schema Pflicht, sobald der Block
 * dasteht, und trägt für sich genommen keine Aussage.
 */
export function hasRelevance(finding: Finding): boolean {
  const relevance = finding.relevance
  if (!relevance) return false
  return (
    relevance.open_items != null ||
    relevance.volume_12m != null ||
    relevance.last_activity_on != null
  )
}

/** Ein Finding gilt als offen, solange niemand darüber entschieden hat. */
export function isOpen(finding: Finding): boolean {
  return finding.status === 'open'
}
