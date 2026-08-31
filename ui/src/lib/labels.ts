/**
 * Deutsche Beschriftungen für die Enum-Werte aus `logic/finding.schema.json`.
 *
 * Die Feldnamen (Seite, Kategorie, Schwere, Schadensklasse, Stufe, Aktionstyp)
 * stammen wörtlich aus `docs/GLOSSARY.md`. Für die *Werte* nennt das Glossar keine
 * deutschen Wörter; die Kategorien folgen `docs/CONCEPT.md` Abschnitt 3
 * („Vollständigkeit/Validität/Konsistenz/Hygiene/Risiko"), der Rest ist hier
 * festgelegt und in `ui/NOTES.md` vermerkt.
 *
 * `labels.test.ts` prüft, dass jede Enum-Konstante aus `@/types/finding` genau
 * eine Beschriftung hat – sonst fällt beim Erweitern des Schemas eine Lücke auf.
 */

import type { DecisionAction, ReasonCode } from '@/types/decision'
import type {
  ActionType,
  Category,
  DamageClass,
  FindingStatus,
  Role,
  Severity,
  Side,
  SourceType,
  Tier,
} from '@/types/finding'

export const SIDE_LABELS: Record<Side, string> = {
  AR: 'Debitoren',
  AP: 'Kreditoren',
  CROSS: 'Übergreifend',
}

/** Kurzform für die Tabellenspalte – die Langform steht im Filter und im Tooltip. */
export const SIDE_SHORT_LABELS: Record<Side, string> = {
  AR: 'AR',
  AP: 'AP',
  CROSS: 'CROSS',
}

export const CATEGORY_LABELS: Record<Category, string> = {
  completeness: 'Vollständigkeit',
  validity: 'Validität',
  consistency: 'Konsistenz',
  hygiene: 'Hygiene',
  risk: 'Risiko',
  duplicate: 'Dublette',
  leakage: 'Geldabfluss',
}

export const SEVERITY_LABELS: Record<Severity, string> = {
  low: 'niedrig',
  medium: 'mittel',
  high: 'hoch',
  critical: 'kritisch',
}

export const DAMAGE_CLASS_LABELS: Record<DamageClass, string> = {
  1: 'Bankdaten – Geldwirkung bei Fehlkorrektur',
  2: 'steuerlich oder vertraglich',
  3: 'reversibel',
}

export const TIER_LABELS: Record<Tier, string> = {
  A: 'A – Soll',
  B: 'B – Vorschlag',
  C: 'C – Hinweis',
  decision: 'Entscheidung',
}

/** Kurzform für Badge und Tabelle. */
export const TIER_SHORT_LABELS: Record<Tier, string> = {
  A: 'A',
  B: 'B',
  C: 'C',
  decision: 'E',
}

export const ACTION_TYPE_LABELS: Record<ActionType, string> = {
  mass_change: 'Massenänderung',
  review: 'Review',
  decision: 'Entscheidung',
  process: 'Prozess',
}

export const STATUS_LABELS: Record<FindingStatus, string> = {
  open: 'offen',
  in_progress: 'in Arbeit',
  done: 'erledigt',
  accepted_risk: 'Risiko akzeptiert',
  rejected: 'abgelehnt',
}

export const ROLE_LABELS: Record<Role, string> = {
  CUSTOMER: 'Debitor',
  VENDOR: 'Kreditor',
}

/** Quellentypen für das Evidenz-Panel (Aufgabe 3), hier schon vollständig gepflegt. */
export const SOURCE_TYPE_LABELS: Record<SourceType, string> = {
  deterministic: 'Regelprüfung',
  vies: 'VIES',
  iban_checksum: 'IBAN-Prüfziffer',
  duplicate_record: 'Dublette',
  invoice: 'Rechnung',
  bank_statement: 'Kontoauszug',
  payment_run: 'Zahllauf',
  change_document: 'Änderungsbeleg',
  statistics: 'Statistik',
  model: 'Modell',
  external_register: 'Externes Register',
  postal_code_list: 'Postleitzahlenverzeichnis',
  policy: 'Policy',
}

/** Beschriftungen der Aktionen auf der Review-Karte. */
export const DECISION_ACTION_LABELS: Record<DecisionAction, string> = {
  accept: 'Übernehmen',
  reject: 'Ablehnen',
  assign: 'Zuweisen',
}

/** Pflichtgründe beim Ablehnen. */
export const REASON_CODE_LABELS: Record<ReasonCode, string> = {
  intentionally_separate: 'bewusst getrennt geführt',
  data_correct: 'Daten sind korrekt',
  not_relevant: 'nicht relevant',
  accepted_risk: 'Risiko akzeptiert',
}

/**
 * Statustext nach einer Entscheidung. „Übernehmen" und „Zuweisen" führen beide auf
 * `in_progress`, sagen aber Verschiedenes – `done` bleibt dem nächsten Lauf
 * vorbehalten, der das Finding nicht mehr meldet (Freigabe Victor, 2026-08-30).
 */
export const DECISION_STATUS_LABELS: Record<DecisionAction, string> = {
  accept: 'freigegeben – Umsetzung offen',
  assign: 'zugewiesen',
  reject: STATUS_LABELS.rejected,
}
