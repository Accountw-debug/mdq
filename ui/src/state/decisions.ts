/**
 * Entscheidungen des Bearbeiters: `finding_id` → Entscheidungssatz.
 *
 * Die geladenen Findings bleiben unverändert – wie in der Pipeline die Rohdaten
 * (CLAUDE.md, Regel 3). Angezeigt wird eine Überlagerung: `applyDecisions` legt
 * Status und `decision` über eine Kopie. Der Export (Aufgabe 7) liest diese Map.
 */

import { statusForDecision } from '@/lib/review'
import type { DecisionRecord } from '@/types/decision'
import type { Finding } from '@/types/finding'

export type DecisionsState = Readonly<Record<string, DecisionRecord>>

export const NO_DECISIONS: DecisionsState = {}

export type DecisionsAction =
  | { type: 'record'; record: DecisionRecord }
  | { type: 'clear'; findingId: string }
  /** Neue Findings-Datei: alte Entscheidungen gehören nicht zum neuen Lauf. */
  | { type: 'reset' }
  /**
   * Entscheidungsdatei eingelesen. Sie **ersetzt** den Stand der Sitzung, sie
   * mischt nicht: „gestern weitergearbeitet" ist ein Zustand, nicht die Summe
   * zweier (Freigabe Victor, 2026-08-30). Gibt es lokale Entscheidungen, fragt
   * die Oberfläche vorher nach.
   */
  | { type: 'import'; records: DecisionsState }

export function decisionsReducer(state: DecisionsState, action: DecisionsAction): DecisionsState {
  switch (action.type) {
    case 'record':
      return { ...state, [action.record.finding_id]: action.record }

    case 'clear': {
      if (!(action.findingId in state)) return state
      const next = { ...state }
      delete next[action.findingId]
      return next
    }

    case 'reset':
      return Object.keys(state).length === 0 ? state : NO_DECISIONS

    case 'import':
      return { ...action.records }
  }
}

/** Status, den die Liste zeigt: der aus dem Lauf, bis eine Entscheidung ihn ersetzt. */
export function effectiveStatus(finding: Finding, decisions: DecisionsState): Finding['status'] {
  const record = decisions[finding.finding_id]
  return record == null ? finding.status : statusForDecision(record)
}

/**
 * Findings mit den Entscheidungen dieser Sitzung. Das Ergebnis bleibt schemakonform:
 * `decision` bekommt nur die vier Felder, die `logic/finding.schema.json` kennt –
 * `action` und `assigned_to` bleiben in der Map (Rückmeldung in `ui/NOTES.md`).
 */
export function applyDecisions(
  findings: readonly Finding[],
  decisions: DecisionsState,
): Finding[] {
  if (Object.keys(decisions).length === 0) return [...findings]
  return findings.map((finding) => {
    const record = decisions[finding.finding_id]
    if (record == null) return finding
    return {
      ...finding,
      status: statusForDecision(record),
      decision: {
        by: record.by,
        at: record.at,
        reason: record.reason,
        reason_code: record.reason_code,
      },
    }
  })
}
