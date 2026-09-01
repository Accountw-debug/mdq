/**
 * Filtern, Suchen, Sortieren und Zählen der Findings – reine Funktionen ohne React.
 *
 * Beträge werden über `parseCents` als `bigint` verglichen, nie über `Number`
 * (CLAUDE.md, Regel 2). Jede Sortierung endet auf `finding_id`, damit dieselbe
 * Findings-Datei immer dieselbe Reihenfolge ergibt (Regel 9).
 */

import { parseCents } from '@/lib/format'
import type {
  ActionType,
  Category,
  Finding,
  FindingStatus,
  Severity,
  Side,
  Tier,
} from '@/types/finding'
import { ACTION_TYPES } from '@/types/finding'

/** Wert eines Filters, der nicht einschränkt. */
export const ALL = 'all'

/** Filterwert für Findings ohne Buchungskreis (`entity.company_code` fehlt oder ist null). */
export const NO_COMPANY_CODE = 'none'

export interface Filters {
  side: Side | typeof ALL
  category: Category | typeof ALL
  severity: Severity | typeof ALL
  tier: Tier | typeof ALL
  companyCode: string | typeof ALL
  status: FindingStatus | typeof ALL
}

export const EMPTY_FILTERS: Filters = {
  side: ALL,
  category: ALL,
  severity: ALL,
  tier: ALL,
  companyCode: ALL,
  status: ALL,
}

export type SortColumn =
  | 'tier'
  | 'severity'
  | 'damage_class'
  | 'side'
  | 'rule_id'
  | 'bp_key'
  | 'title'
  | 'impact'
  | 'status'

export type SortDirection = 'asc' | 'desc'

export interface Sort {
  column: SortColumn
  direction: SortDirection
}

/** Spec: Euro-Wirkung absteigend, dann Schwere. */
export const DEFAULT_SORT: Sort = { column: 'impact', direction: 'desc' }

const SEVERITY_RANK: Record<Severity, number> = { low: 0, medium: 1, high: 2, critical: 3 }
const TIER_RANK: Record<Tier, number> = { A: 0, B: 1, C: 2, decision: 3 }
const SIDE_RANK: Record<Side, number> = { AR: 0, AP: 1, CROSS: 2 }
const STATUS_RANK: Record<FindingStatus, number> = {
  open: 0,
  in_progress: 1,
  done: 2,
  accepted_risk: 3,
  rejected: 4,
}

/** Buchungskreis eines Findings als Filterwert; fehlt er, gilt `NO_COMPANY_CODE`. */
export function companyCodeOf(finding: Finding): string {
  return finding.entity.company_code ?? NO_COMPANY_CODE
}

/** Euro-Wirkung in Cents; ohne `impact_eur` zählt das Finding als 0. */
export function impactCents(finding: Finding): bigint {
  const amount = finding.impact_eur?.amount
  return amount == null ? 0n : parseCents(amount)
}

function compareBigint(a: bigint, b: bigint): number {
  if (a < b) return -1
  if (a > b) return 1
  return 0
}

function compareNumber(a: number, b: number): number {
  return a - b
}

/** Ohne `Intl`/`localeCompare`: die Reihenfolge muss auf jedem Rechner gleich sein. */
function compareText(a: string, b: string): number {
  const left = a.toLowerCase()
  const right = b.toLowerCase()
  if (left < right) return -1
  if (left > right) return 1
  return 0
}

function compareByColumn(a: Finding, b: Finding, column: SortColumn): number {
  switch (column) {
    case 'tier':
      return compareNumber(TIER_RANK[a.tier], TIER_RANK[b.tier])
    case 'severity':
      return compareNumber(SEVERITY_RANK[a.severity], SEVERITY_RANK[b.severity])
    case 'damage_class':
      return compareNumber(a.damage_class, b.damage_class)
    case 'side':
      return compareNumber(SIDE_RANK[a.side], SIDE_RANK[b.side])
    case 'rule_id':
      return compareText(a.rule_id, b.rule_id)
    case 'bp_key':
      return compareText(a.entity.bp_key, b.entity.bp_key)
    case 'title':
      return compareText(a.title, b.title)
    case 'impact':
      return compareBigint(impactCents(a), impactCents(b))
    case 'status':
      return compareNumber(STATUS_RANK[a.status], STATUS_RANK[b.status])
  }
}

/**
 * Sortiert nach der gewählten Spalte, danach immer nach Schwere absteigend und
 * zuletzt nach `finding_id` – der Gleichstand wird nie dem Zufall überlassen.
 */
export function sortFindings(findings: readonly Finding[], sort: Sort = DEFAULT_SORT): Finding[] {
  const factor = sort.direction === 'desc' ? -1 : 1
  return [...findings].sort((a, b) => {
    const primary = compareByColumn(a, b, sort.column) * factor
    if (primary !== 0) return primary
    if (sort.column !== 'severity') {
      const bySeverity = compareNumber(SEVERITY_RANK[b.severity], SEVERITY_RANK[a.severity])
      if (bySeverity !== 0) return bySeverity
    }
    return compareText(a.finding_id, b.finding_id)
  })
}

export function matchesFilters(finding: Finding, filters: Filters): boolean {
  if (filters.side !== ALL && finding.side !== filters.side) return false
  if (filters.category !== ALL && finding.category !== filters.category) return false
  if (filters.severity !== ALL && finding.severity !== filters.severity) return false
  if (filters.tier !== ALL && finding.tier !== filters.tier) return false
  if (filters.status !== ALL && finding.status !== filters.status) return false
  if (filters.companyCode !== ALL && companyCodeOf(finding) !== filters.companyCode) return false
  return true
}

/** Volltextsuche über bp_key, display_name, Titel und Regel-ID. */
export function matchesSearch(finding: Finding, search: string): boolean {
  const needle = search.trim().toLowerCase()
  if (needle === '') return true
  const haystack = [
    finding.entity.bp_key,
    finding.entity.display_name ?? '',
    finding.title,
    finding.rule_id,
  ]
  return haystack.some((field) => field.toLowerCase().includes(needle))
}

export interface Query {
  tab: ActionType
  filters: Filters
  search: string
  sort: Sort
}

/** Findings nach Filter und Suche – noch ohne Tab-Einschränkung. */
export function applyFiltersAndSearch(
  findings: readonly Finding[],
  filters: Filters,
  search: string,
): Finding[] {
  return findings.filter(
    (finding) => matchesFilters(finding, filters) && matchesSearch(finding, search),
  )
}

/** Die sichtbare Liste eines Tabs: Filter, Suche, Aktionstyp, Sortierung. */
export function selectVisibleFindings(findings: readonly Finding[], query: Query): Finding[] {
  const matching = applyFiltersAndSearch(findings, query.filters, query.search).filter(
    (finding) => finding.action_type === query.tab,
  )
  return sortFindings(matching, query.sort)
}

/**
 * Position eines Findings in der sichtbaren Liste – `-1`, wenn es nicht darin
 * vorkommt. Der Index ist die Schnittstelle zur Tabelle: mit Virtualisierung ist
 * die gewählte Zeile womöglich gar nicht gerendert und nur über ihn erreichbar.
 */
export function indexOfId(findings: readonly Finding[], findingId: string | null): number {
  if (findingId == null) return -1
  return findings.findIndex((finding) => finding.finding_id === findingId)
}

/**
 * Zähler der Tabs – nach Filter und Suche, damit die Zahl am Tab zur Tabelle passt.
 * Jeder Aktionstyp kommt vor, auch mit 0 (die Beispiele haben keine Massenänderung).
 */
export function countByActionType(
  findings: readonly Finding[],
  filters: Filters,
  search: string,
): Record<ActionType, number> {
  const counts = Object.fromEntries(ACTION_TYPES.map((type) => [type, 0])) as Record<
    ActionType,
    number
  >
  for (const finding of applyFiltersAndSearch(findings, filters, search)) {
    counts[finding.action_type] += 1
  }
  return counts
}

/**
 * Tab, mit dem ein frisch geladener Lauf öffnet: der erste Aktionstyp in der
 * Reihenfolge von `ACTION_TYPES`, zu dem der Lauf mindestens ein Finding hat.
 * Massenänderung steht dort vorn, und genau darum geht es – wer den Lauf öffnet,
 * soll die Stufe-A-Gruppen sehen und nicht erst danach suchen (Beobachtung
 * Victor, 2026-09-01).
 *
 * Gezählt wird ungefiltert: die Startansicht beschreibt den Lauf, nicht eine
 * Filterung. Ein Lauf ohne Findings öffnet auf `review`.
 */
export function startTab(findings: readonly Finding[]): ActionType {
  const present = new Set(findings.map((finding) => finding.action_type))
  return ACTION_TYPES.find((type) => present.has(type)) ?? 'review'
}

/**
 * Auswahlliste des Buchungskreis-Filters: eindeutig und sortiert, mit eigenem
 * Eintrag für Findings ohne Buchungskreis. Basis sind alle Findings, damit die
 * Liste beim Filtern nicht springt.
 */
export function companyCodeOptions(findings: readonly Finding[]): string[] {
  const codes = new Set<string>()
  let hasNone = false
  for (const finding of findings) {
    const code = finding.entity.company_code
    if (code == null) hasNone = true
    else codes.add(code)
  }
  const sorted = [...codes].sort(compareText)
  return hasNone ? [...sorted, NO_COMPANY_CODE] : sorted
}
