/**
 * Dubletten-Vergleich (Spec Sprint 5, Aufgabe 4) – reine Funktionen, ohne React.
 *
 * Die Spec verlangt eine Vergleichstabelle über neun Felder je Konto. Das Finding
 * liefert davon heute drei, und die nur als Fließtext in `current.display`, an ` | `
 * aneinandergereiht. Die übrigen sechs stehen als Prosa in `proposed.display` oder in
 * Evidenz-Notizen – und dort jeweils nur für ein Konto. Sie werden hier **nicht**
 * herausgelesen: aus „45.210 € OP" eine Zeile „Offene Posten" zu bauen, die dem einen
 * Konto einen Betrag gibt und dem anderen keinen, wäre geraten, nicht gelesen. Was
 * fehlt, steht als `missingFields` in der Tabelle – benannt, nicht verschwiegen
 * (CLAUDE.md, Regel 4). Die Schema-Rückmeldung dazu heißt `entity.records`.
 */

import type { Evidence, Finding } from '@/types/finding'

/** Feldliste der Spec, in ihrer Reihenfolge. Woraus die Tabelle bestehen soll. */
export const SPEC_FIELDS = [
  'Name',
  'Straße',
  'PLZ/Ort',
  'Land',
  'USt-ID',
  'IBAN',
  'Zahlungsbedingung',
  'Offene Posten',
  'Letzte Zahlung',
] as const

/** Beschriftung der Zeile, wenn sich die Adresszeile nicht sauber zerlegen lässt. */
export const RAW_ROW_LABEL = 'Angabe'

export interface DuplicateAccount {
  /** Schlüssel wie im Finding, mit Rollenpräfix: `C:0000100234`. */
  bpKey: string
  /** Führendes Konto laut `proposed.value` – bekommt die Krone. */
  isLead: boolean
}

export interface DuplicateRow {
  label: string
  /** Ein Eintrag je Konto, in der Reihenfolge von `accounts`. `null` = keine Angabe. */
  cells: (string | null)[]
  /** Weichen die Werte voneinander ab? Nur dann wird die Zeile hervorgehoben. */
  differs: boolean
}

export interface DuplicateComparison {
  accounts: DuplicateAccount[]
  rows: DuplicateRow[]
  /** Match-Gründe als Chips, aus der Evidenz mit `source_type: model`. */
  chips: string[]
  /** Notizen derselben Evidenz, als Satz unter den Chips. */
  matchNote: string | null
  /** Felder der Spec, die das Finding nicht hergibt. */
  missingFields: string[]
}

/**
 * Vergleichbar machen: Rollenpräfix (`C:`/`V:`) und führende Nullen weg.
 *
 * `entity.bp_key` trägt das Präfix, `current.value` und `proposed.value` tragen es
 * nicht. In den Daten bleiben die führenden Nullen erhalten (CLAUDE.md, Regel 2) –
 * verglichen wird trotzdem ohne sie, sonst scheitert die Zuordnung an einer Null.
 */
export function normalizeAccount(raw: string): string {
  return raw.trim().replace(/^[A-Z]:/, '').replace(/^0+(?=\d)/, '')
}

/** Bezeichnet `raw` dasselbe Konto wie `bpKey`? */
export function accountMatches(bpKey: string, raw: string | null | undefined): boolean {
  if (raw == null || raw.trim() === '') return false
  const normalized = normalizeAccount(raw)
  return normalized !== '' && normalized === normalizeAccount(bpKey)
}

/** An ` | ` zerlegen; `null`, wenn nichts dasteht. */
function splitSegments(text: string | null | undefined): string[] | null {
  if (text == null || text.trim() === '') return null
  return text.split('|').map((part) => part.trim())
}

/**
 * Konten des Clusters: das Finding selbst zuerst, dann `related_bp_keys`.
 * Doppelte Schlüssel fallen raus – eine Spalte je Konto.
 */
export function duplicateAccounts(finding: Finding): string[] {
  const keys = [finding.entity.bp_key, ...(finding.entity.related_bp_keys ?? [])]
  return keys.filter((key, index) => key.trim() !== '' && keys.indexOf(key) === index)
}

/**
 * Ordnet die Segmente von `current.value` den Konten zu: Ergebnis[i] ist der Index
 * des Segments, das zu `accounts[i]` gehört.
 *
 * Bewusst über den Schlüsselvergleich statt über die Position. Dass das erste Segment
 * zum ersten Konto gehört, steht nirgends; wenn es nicht nachweisbar ist, gibt es
 * keine Tabelle, sondern den gewohnten Ist|Soll-Abschnitt.
 */
function mapSegmentsToAccounts(accounts: string[], segments: string[]): number[] | null {
  if (segments.length !== accounts.length) return null
  const mapping: number[] = []
  for (const account of accounts) {
    const index = segments.findIndex((segment) => accountMatches(account, segment))
    if (index === -1 || mapping.includes(index)) return null
    mapping.push(index)
  }
  return mapping
}

/** Match-Gründe aus der Evidenz mit `source_type: model`. */
export function matchReasons(evidence: readonly Evidence[]): {
  chips: string[]
  note: string | null
} {
  const model = evidence.filter((entry) => entry.source_type === 'model')
  const chips = model
    .flatMap((entry) => (entry.value ?? '').split(','))
    .map((chip) => chip.trim())
    .filter((chip) => chip !== '')
  const notes = model
    .map((entry) => entry.note?.trim())
    .filter((note): note is string => note != null && note !== '')
  return { chips, note: notes.length > 0 ? notes.join(' ') : null }
}

/**
 * Zerlegt eine Adresszeile „Name, Straße, PLZ Ort" in ihre drei Teile.
 * `null`, sobald es nicht genau drei sind – dann steht die Zeile wörtlich da.
 */
function splitAddress(segment: string): [string, string, string] | null {
  const parts = segment.split(',').map((part) => part.trim())
  if (parts.length !== 3 || parts.some((part) => part === '')) return null
  return [parts[0], parts[1], parts[2]]
}

function toRow(label: string, cells: (string | null)[]): DuplicateRow {
  const distinct = new Set(cells.map((cell) => cell ?? ''))
  return { label, cells, differs: distinct.size > 1 }
}

/**
 * Der ganze Vergleich, oder `null`, wenn die Daten ihn nicht tragen.
 *
 * `null` heißt: die Review-Karte zeigt Ist|Soll wie bei jedem anderen Finding. Eine
 * halbe Tabelle wäre schlechter als gar keine.
 */
export function buildDuplicateComparison(finding: Finding): DuplicateComparison | null {
  const keys = duplicateAccounts(finding)
  if (keys.length < 2) return null

  const valueSegments = splitSegments(finding.current.value)
  if (valueSegments == null) return null
  const mapping = mapSegmentsToAccounts(keys, valueSegments)
  if (mapping == null) return null

  const accounts: DuplicateAccount[] = keys.map((bpKey) => ({
    bpKey,
    isLead: accountMatches(bpKey, finding.proposed?.value),
  }))

  const rows = buildRows(finding.current.display, mapping)
  const covered = new Set(rows.map((row) => row.label))
  const missingFields = SPEC_FIELDS.filter((field) => !covered.has(field))

  const { chips, note } = matchReasons(finding.evidence ?? [])

  return { accounts, rows, missingFields, chips, matchNote: note }
}

/**
 * Die Zeilen aus `current.display`. Drei benannte Zeilen nur, wenn sich **jedes**
 * Segment in genau Name/Straße/PLZ+Ort zerlegen lässt; sonst eine Zeile mit dem
 * unveränderten Text. Gemischt wird nicht – sonst stünde in einer Spalte ein Name,
 * wo in der anderen die ganze Anschrift steht.
 */
function buildRows(display: string | null | undefined, mapping: number[]): DuplicateRow[] {
  const segments = splitSegments(display)
  // Genauso viele Segmente wie Konten, sonst ist die Zuordnung nicht belegt.
  if (segments == null || segments.length !== mapping.length) return []

  const ordered = mapping.map((index) => segments[index])
  const addresses = ordered.map(splitAddress)

  if (addresses.every((address) => address != null)) {
    const parts = addresses as [string, string, string][]
    return [
      toRow('Name', parts.map((part) => part[0])),
      toRow('Straße', parts.map((part) => part[1])),
      toRow('PLZ/Ort', parts.map((part) => part[2])),
    ]
  }

  return [toRow(RAW_ROW_LABEL, ordered.map((segment) => (segment === '' ? null : segment)))]
}
