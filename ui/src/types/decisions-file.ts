/**
 * Der Vertrag der Datei `decisions.json` – Export **und** Import.
 *
 * Was das UI schreibt, muss es am nächsten Tag wieder einlesen können: derselbe
 * Bearbeiter, derselbe Lauf, Arbeit fortsetzen statt neu anfangen (ui/NOTES.md,
 * 2026-08-30). Deshalb steht die Version in der Datei und nicht im Kopf.
 *
 * Versionsregel:
 * - Zusätzliche, optionale Felder lassen `format_version` unverändert. Ein älterer
 *   Leser nennt sie als unbekannt (Regel 4 – nichts stumm verwerfen), liest den
 *   Rest aber weiter.
 * - Alles, was einen älteren Leser falsch verstehen ließe (Feld entfällt, Bedeutung
 *   ändert sich, neuer Pflichtwert), erhöht `format_version`.
 * - Ein Leser nimmt genau die Versionen, die er kennt; jede andere bricht ab.
 *
 * `sample_reviewed` (die geprüfte Stichprobe je Regelgruppe) kam mit Aufgabe 7
 * dazu – additiv, ohne Versionssprung: ein älterer Leser nennt das Feld als
 * unbekannt und liest die Entscheidungen trotzdem.
 */

import type { DecisionRecord } from '@/types/decision'
import type { IsoDate, IsoDateTime } from '@/types/finding'

export const DECISIONS_FORMAT = 'mdq.decisions'

/** Die einzige Version, die dieses UI schreibt und liest. */
export const DECISIONS_FORMAT_VERSION = 1

/**
 * Ausgang einer Stichprobe je Regelgruppe (Spec Sprint 5, Aufgabe 7).
 *
 * `released`: die Stichprobe wurde vollständig übernommen, die Gruppe ist
 * freigegeben – `applied_finding_ids` nennt die Findings, die diese Freigabe
 * entschieden hat (die Stichprobe selbst trägt ihre eigenen Entscheidungen).
 * `blocked`: ein Finding der Stichprobe wurde abgelehnt; die Gruppenfreigabe ist
 * für diesen Lauf gesperrt, die übrigen Findings bleiben einzeln entscheidbar
 * (Freigabe Victor, 2026-08-30).
 *
 * Der Satz steht in der Datei, damit die Sperre einen Export und den Import am
 * nächsten Tag überlebt – sonst wäre „endgültig" nur bis zum Feierabend wahr.
 */
export interface SampleReview {
  rule_id: string
  outcome: 'released' | 'blocked'
  /** Die gezogenen und geprüften Findings, in Prüfreihenfolge. */
  sampled_finding_ids: string[]
  /** Nur bei `released`: die von der Freigabe entschiedenen Findings. */
  applied_finding_ids: string[]
  /** Nur bei `blocked`: das abgelehnte Finding der Stichprobe. */
  blocked_by_finding_id: string | null
  by: string
  at: IsoDateTime
}

export const SAMPLE_OUTCOMES = ['released', 'blocked'] as const

export interface DecisionsFile {
  format: typeof DECISIONS_FORMAT
  format_version: number
  /**
   * Der Lauf, zu dem die Entscheidungen gefallen sind – mitsamt Datenstand und
   * Versionen. Beim Einlesen ist das die Probe, ob Datei und Bildschirm zusammengehören.
   */
  run_id: string
  data_as_of: IsoDate
  engine_version: string
  pack_version: string
  exported_at: IsoDateTime
  /** Der Bearbeiter aus dem Datenstand-Banner; steht zusätzlich in jedem Satz als `by`. */
  exported_by: string
  decisions: DecisionRecord[]
  /** Fehlt, solange in der Sitzung keine Stichprobe geprüft wurde. */
  sample_reviewed?: SampleReview[]
}
