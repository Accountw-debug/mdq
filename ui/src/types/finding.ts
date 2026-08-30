/**
 * TypeScript-Abbild von `logic/finding.schema.json`.
 *
 * Von Hand geschrieben, damit die Union-Types und die Nullbarkeit exakt dem Schema
 * entsprechen. Die Enum-Listen liegen als `as const`-Arrays vor: daraus werden die
 * Typen abgeleitet, und `finding.enums.test.ts` gleicht sie zur Testzeit gegen das
 * Schema ab, damit die Kopie nicht auseinanderläuft.
 *
 * Beträge sind durchgehend `string` mit zwei Dezimalen ("32000.00") – nie `number`
 * (CLAUDE.md, Regel 2). Rechnen nur über `parseCents`/`sumEur` in `@/lib/format`.
 */

export const SIDES = ['AR', 'AP', 'CROSS'] as const
export type Side = (typeof SIDES)[number]

export const CATEGORIES = [
  'completeness',
  'validity',
  'consistency',
  'hygiene',
  'risk',
  'duplicate',
  'leakage',
] as const
export type Category = (typeof CATEGORIES)[number]

export const SEVERITIES = ['low', 'medium', 'high', 'critical'] as const
export type Severity = (typeof SEVERITIES)[number]

/** 1 = Geldwirkung bei Fehlkorrektur (Bankdaten), 2 = steuerlich/vertraglich, 3 = reversibel */
export const DAMAGE_CLASSES = [1, 2, 3] as const
export type DamageClass = (typeof DAMAGE_CLASSES)[number]

/** A Soll (>= 99 %), B Vorschlag (>= 90 %), C Hinweis, decision = Entscheidung des Kunden */
export const TIERS = ['A', 'B', 'C', 'decision'] as const
export type Tier = (typeof TIERS)[number]

export const ACTION_TYPES = ['mass_change', 'review', 'decision', 'process'] as const
export type ActionType = (typeof ACTION_TYPES)[number]

export const ROLES = ['CUSTOMER', 'VENDOR'] as const
export type Role = (typeof ROLES)[number]

export const SOURCE_TYPES = [
  'deterministic',
  'vies',
  'iban_checksum',
  'duplicate_record',
  'invoice',
  'bank_statement',
  'payment_run',
  'change_document',
  'statistics',
  'model',
  'external_register',
  'postal_code_list',
  'policy',
] as const
export type SourceType = (typeof SOURCE_TYPES)[number]

export const STATUSES = ['open', 'in_progress', 'done', 'accepted_risk', 'rejected'] as const
export type FindingStatus = (typeof STATUSES)[number]

/** Betrag als String mit zwei Dezimalen, z. B. "32000.00" oder "-8930.00". Nie float. */
export type EurAmount = string

/** ISO-Datum "2026-08-28". */
export type IsoDate = string

/** ISO-Zeitstempel in UTC, z. B. "2026-08-30T09:15:00Z". */
export type IsoDateTime = string

export interface FindingDocument {
  company_code: string
  fiscal_year: string
  document_no: string
  /** Im Schema nicht unter `required` – kann fehlen oder null sein. */
  line_item?: string | null
}

export interface FindingEntity {
  /** C:<KUNNR> oder V:<LIFNR> */
  bp_key: string
  role: Role
  company_code?: string | null
  display_name?: string | null
  /** Weitere BPs, z. B. Dubletten-Cluster oder Gegenpartei bei CROSS */
  related_bp_keys?: string[]
  /** Beteiligte Belege, z. B. Doppelzahlungspaar */
  documents?: FindingDocument[]
}

export interface FindingRelevance {
  open_items_eur?: EurAmount
  volume_12m_eur?: EurAmount
  last_activity_on?: IsoDate | null
}

export interface FindingCurrent {
  source_table: string
  source_field: string
  value: string | null
  /** Lesbare Darstellung, z. B. decodierte Zahlungsbedingung */
  display?: string | null
}

export interface ProposedOption {
  label: string
  consequence: string
}

export interface FindingProposed {
  value: string | null
  display?: string | null
  /** Quellenlage in Klartext */
  source_summary: string
  /** Bei Stufe `decision`: aufbereitete Optionen */
  options?: ProposedOption[]
}

export interface Evidence {
  source_type: SourceType
  /** Belegnummer, BP-Schlüssel, Abfrage-ID, Datei */
  reference: string
  value: string | null
  observed_at?: IsoDate | null
  /** true = stützt das Soll, false = widerspricht */
  agrees: boolean
  note?: string | null
}

export interface ImpactEur {
  amount: EurAmount
  /** ISO-4217, z. B. "EUR" */
  currency: string
  /** Offengelegte Rechnung, z. B. "32000.00 × 2 % = 640.00" */
  formula: string
  /** Gutschriften/Stornos, die abgezogen wurden */
  netted_against?: string | null
}

export interface Remediation {
  /** z. B. XD02, XK02, FB05, XD05, XD06 */
  sap_transaction: string
  /** Reiter/Feld, z. B. "Steuerung → USt-IdNr." */
  path?: string | null
  field?: string | null
  mass_change_eligible: boolean
  steps?: string[]
}

export interface FindingDecision {
  by: string
  at: IsoDateTime
  reason: string
  /** z. B. intentionally_separate, data_correct, not_relevant */
  reason_code?: string | null
}

export interface Finding {
  /** Muster ^F-[a-f0-9]{12}$ */
  finding_id: string
  run_id: string
  /** Muster ^(AR|AP|CROSS)-(COM|VAL|CON|HYG|RSK|DUP|LEA)-[0-9]{3}$ */
  rule_id: string
  rule_version: string
  engine_version: string
  /** Version des Regelpakets/Wörterbuchs */
  pack_version: string
  side: Side
  category: Category
  severity: Severity
  damage_class: DamageClass
  tier: Tier
  action_type: ActionType
  /** Kurzüberschrift für Listen, max. 120 Zeichen */
  title?: string
  entity: FindingEntity
  relevance?: FindingRelevance
  current: FindingCurrent
  /** null bei Stufe C/decision ohne Vorschlag. Stufe A und B haben immer ein Soll. */
  proposed?: FindingProposed | null
  evidence?: Evidence[]
  impact_eur?: ImpactEur | null
  /** Warum ist das ein Problem, was passiert ohne Behebung */
  why: string
  /** Was passiert, wenn der Vorschlag falsch übernommen wird */
  if_wrong: string
  remediation: Remediation
  related_finding_ids?: string[]
  status: FindingStatus
  decision?: FindingDecision | null
  /** Datum des Exports beim Kunden */
  data_as_of: IsoDate
  created_at: IsoDateTime
}

/**
 * Kopf des Laufs. Wird von `scripts/build-data.mjs` aus den Findings abgeleitet
 * bzw. von der Engine als `runs/<run_id>/run.json` geliefert.
 */
export interface RunInfo {
  run_id: string
  data_as_of: IsoDate
  engine_version: string
  pack_version: string
  /** Anzahl geladener Quelltabellen. Das UI kennt die Ladeschicht nicht -> 0 aus dem Build-Skript. */
  tables_loaded: number
  /** Eindeutige, sortierte Buchungskreise aus den Findings */
  company_codes: string[]
}
