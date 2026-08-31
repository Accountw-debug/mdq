/**
 * TypeScript-Abbild von `logic/finding.schema.json` (Schema-Version 1.1).
 *
 * Von Hand geschrieben, damit die Union-Types und die Nullbarkeit exakt dem Schema
 * entsprechen. Die Enum-Listen liegen als `as const`-Arrays vor: daraus werden die
 * Typen abgeleitet, und `finding.enums.test.ts` gleicht sie zur Testzeit gegen das
 * Schema ab, damit die Kopie nicht auseinanderläuft.
 *
 * Beträge sind durchgehend `string` mit zwei Dezimalen ("32000.00") – nie `number`
 * (CLAUDE.md, Regel 2). Rechnen nur über `parseCents`/`sumEur` in `@/lib/format`.
 * Die Währung steht immer neben dem Betrag; sie steckt seit D-030 nicht mehr im
 * Feldnamen (`open_items` + `currency`, nicht `open_items_eur`).
 *
 * Optional ist hier genau das, was im Schema nicht unter `required` steht. Alle
 * Felder aus D-069 (`evidence[].reference_kind`, die Beleg-Erweiterungen,
 * `entity.records`, `proposed.golden_record`, `decision.assigned_to`) sind optional:
 * eine Regel füllt, was sie hat.
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

/**
 * Was die Referenz einer Evidenz ist (D-069). `source_type` sagt das nicht:
 * `1000/2026/1900004411` (Beleg), `KNA1.LAND1` (Stammfeld) und `cluster-000412`
 * stehen alle unter `deterministic` bzw. `model`.
 */
export const REFERENCE_KINDS = [
  'document',
  'master_field',
  'cluster',
  'external_query',
  'statement',
  'netting',
  'payment_run',
  'policy',
] as const
export type ReferenceKind = (typeof REFERENCE_KINDS)[number]

export const STATUSES = ['open', 'in_progress', 'done', 'accepted_risk', 'rejected'] as const
export type FindingStatus = (typeof STATUSES)[number]

/** Betrag als String mit zwei Dezimalen, z. B. "32000.00" oder "-8930.00". Nie float. */
export type EurAmount = string

/** ISO-4217-Code, z. B. "EUR". Steht immer neben dem Betrag (Regel 2). */
export type CurrencyCode = string

/** ISO-Datum "2026-08-28". */
export type IsoDate = string

/** ISO-Zeitstempel in UTC, z. B. "2026-08-30T09:15:00Z". */
export type IsoDateTime = string

/**
 * IBAN nur maskiert: höchstens die ersten vier und die letzten vier Zeichen sichtbar,
 * dazwischen `…`, `...` oder `***` – z. B. "DE44 …49 32". Eine vollständige IBAN
 * lehnt das Schema per Pattern ab (Regel 8, D-069 Punkt 3).
 */
export type MaskedIban = string

export interface FindingDocument {
  company_code: string
  fiscal_year: string
  document_no: string
  /** Ab hier alles optional – eine Regel liefert es, sobald sie es hat (D-069). */
  line_item?: string | null
  /** Referenz des Belegs (XBLNR), z. B. "RE-4711" */
  reference?: string | null
  /** Belegdatum (BLDAT) */
  document_date?: IsoDate | null
  /** Ausgleichsdatum (AUGDT), „bezahlt am" */
  cleared_on?: IsoDate | null
  amount?: EurAmount | null
  currency?: CurrencyCode | null
}

/**
 * Felder eines Kontos für den Feld-für-Feld-Vergleich. Dieselbe Liste wie in
 * `proposed.golden_record`; ein unbekannter Feldname ist ein Fehler, kein stiller
 * Zusatz (Regel 4). Was das Konto nicht hergibt, bleibt weg oder ist `null`.
 */
export interface RecordFields {
  name?: string | null
  street?: string | null
  postal_code?: string | null
  city?: string | null
  /** ISO-2, wie LAND1 */
  country?: string | null
  vat_id?: string | null
  iban_masked?: MaskedIban | null
  /** Schlüssel wie ZTERM */
  payment_terms?: string | null
  /** Offene Posten dieses Kontos in der Hauswährung */
  open_items?: EurAmount | null
  /** Hauswährung zu `open_items` (Regel 2) */
  currency?: CurrencyCode | null
  last_activity_on?: IsoDate | null
}

/**
 * Je beteiligtem Konto ein strukturierter Datensatz. Vorgesehen für
 * `duplicate`-Findings, nicht darauf beschränkt (D-069 Punkt 4).
 */
export interface EntityRecord {
  bp_key: string
  fields: RecordFields
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
  /** Ein Eintrag je Konto des Clusters – Grundlage des Feld-für-Feld-Vergleichs */
  records?: EntityRecord[]
}

/**
 * Gewichtung des Geschäftspartners in der **Hauswährung des Buchungskreises**.
 * Die Beträge sind nicht umgerechnet; `currency` gehört zwingend dazu (Regel 2).
 */
export interface FindingRelevance {
  open_items?: EurAmount
  volume_12m?: EurAmount
  /** Hauswährung – im Schema das einzige Pflichtfeld des Blocks */
  currency: CurrencyCode
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

/** Der beste Wert eines Feldes mit seiner Herkunft (Glossar: Golden Record). */
export interface GoldenRecordEntry {
  value: string | null
  /** Konto, aus dem der Wert stammt */
  source_bp_key: string
  /** Wodurch der Wert belegt ist – dieselbe Liste wie bei `evidence` */
  source_type: SourceType
}

/**
 * Je Feld der beste Wert mit Quelle. `proposed.value` nennt das führende Konto,
 * dieses Feld die Herkunft je Einzelwert – dieselben Feldnamen wie `RecordFields`.
 */
export type GoldenRecord = { [Field in keyof RecordFields]?: GoldenRecordEntry }

export interface FindingProposed {
  value: string | null
  display?: string | null
  /** Quellenlage in Klartext */
  source_summary: string
  /** Bei Stufe `decision`: aufbereitete Optionen */
  options?: ProposedOption[]
  /** Bei Dubletten: je Feld der beste Wert mit Herkunft */
  golden_record?: GoldenRecord
}

export interface Evidence {
  source_type: SourceType
  /** Belegnummer, BP-Schlüssel, Abfrage-ID, Datei */
  reference: string
  /** Was die Referenz ist – fehlt, wo sie in keinen der acht Werte passt */
  reference_kind?: ReferenceKind
  value: string | null
  observed_at?: IsoDate | null
  /** true = stützt das Soll, false = widerspricht */
  agrees: boolean
  note?: string | null
}

export interface ImpactEur {
  amount: EurAmount
  /** ISO-4217, z. B. "EUR" */
  currency: CurrencyCode
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
  /** Bearbeiter, dem der Fall nach der Entscheidung zugewiesen ist */
  assigned_to?: string
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
  /** Kurzüberschrift für Listen, 1 bis 120 Zeichen. Pflicht seit dem Schema-Stand von D-069. */
  title: string
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
 * Kopf des Laufs. Die Engine schreibt ihn ab Sprint 3 als `runs/<run_id>/run.json`
 * neben `findings.json`; das UI liest daraus die hier genannten Felder und lässt
 * den Rest der Datei (Dateiliste, Regelbilanz, Rejects) unberührt.
 *
 * `scripts/build-data.mjs` erzeugt denselben Kopf ersatzweise für die sechs
 * Beispiel-Findings, wenn kein Lauf vorliegt.
 */
export interface RunInfo {
  run_id: string
  data_as_of: IsoDate
  engine_version: string
  pack_version: string
  /** Anzahl geladener Quelltabellen. Kommt aus `run.json`; ohne Lauf steht hier 0. */
  tables_loaded: number
  /** Buchungskreise des Laufs, wie `run.json` sie nennt – keine Ableitung aus den Findings. */
  company_codes: string[]
}
