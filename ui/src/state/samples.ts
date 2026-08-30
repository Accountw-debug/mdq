/**
 * Geprüfte Stichproben je Regelgruppe: `rule_id` → Ausgang (Spec Sprint 5, Aufgabe 7).
 *
 * Eigener Zustand neben den Entscheidungen: die Freigabe schreibt zwar
 * Entscheidungen, ist selbst aber keine – sie ist die Begründung dafür, dass eine
 * ganze Gruppe ohne Einzelprüfung entschieden wurde. Die Sperre nach einer
 * Ablehnung ließe sich aus den Entscheidungen allein gar nicht ablesen.
 *
 * Wie die Entscheidungen lebt der Zustand nur in der Sitzung und geht über
 * `decisions.json` (Feld `sample_reviewed`) raus und wieder rein.
 */

import type { SampleReview } from '@/types/decisions-file'

export type SamplesState = Readonly<Record<string, SampleReview>>

export const NO_SAMPLES: SamplesState = {}

export type SamplesAction =
  | { type: 'record'; review: SampleReview }
  /** Neue Findings-Datei: die Stichprobe gehörte zum alten Lauf. */
  | { type: 'reset' }
  /** Entscheidungsdatei eingelesen – sie ersetzt den Stand, sie mischt nicht. */
  | { type: 'import'; reviews: SamplesState }

export function samplesReducer(state: SamplesState, action: SamplesAction): SamplesState {
  switch (action.type) {
    case 'record':
      return { ...state, [action.review.rule_id]: action.review }

    case 'reset':
      return Object.keys(state).length === 0 ? state : NO_SAMPLES

    case 'import':
      return { ...action.reviews }
  }
}
