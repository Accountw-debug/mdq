/**
 * Entscheidungen des Bearbeiters – ein **UI-eigener** Typ, kein Abbild des Schemas.
 *
 * `logic/finding.schema.json` kennt unter `decision` nur `by`, `at`, `reason` und
 * `reason_code`. Was hier zusätzlich steht (`action`, `assigned_to`), braucht die
 * Bedienung: der Statustext hängt an der Aktion, und für „Zuweisen" hat das Schema
 * kein Feld (Rückmeldung in `ui/NOTES.md`). Beim Export (Aufgabe 7) wird daraus
 * `[{finding_id, action, reason_code, reason, assigned_to, by, at}]`.
 */

import type { IsoDateTime } from '@/types/finding'

export const DECISION_ACTIONS = ['accept', 'reject', 'assign'] as const
export type DecisionAction = (typeof DECISION_ACTIONS)[number]

/** Pflichtauswahl beim Ablehnen (Spec Sprint 5, Aufgabe 3). */
export const REASON_CODES = [
  'intentionally_separate',
  'data_correct',
  'not_relevant',
  'accepted_risk',
] as const
export type ReasonCode = (typeof REASON_CODES)[number]

export interface DecisionRecord {
  finding_id: string
  action: DecisionAction
  /** Pflicht beim Ablehnen, sonst `null`. */
  reason_code: ReasonCode | null
  /** Klartext; nie leer – ohne Freitext steht hier der abgeleitete Grund. */
  reason: string
  /** Nur bei `assign`: an wen. Im Schema gibt es dafür kein Feld. */
  assigned_to: string | null
  by: string
  at: IsoDateTime
}
