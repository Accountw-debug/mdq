/**
 * Belegpaar-Ansicht (Spec Sprint 5, Aufgabe 5) – reine Funktionen, ohne React.
 *
 * `entity.documents` trägt je Beleg nur den Schlüssel (`BUKRS/GJAHR/BELNR` und
 * Position). Die von der Spec verlangten Kartenfelder – Referenz, Datum, Betrag –
 * stehen dort nicht; sie stecken im Text der Evidenz, die über
 * `reference == "<BUKRS>/<GJAHR>/<BELNR>"` **eindeutig** zu genau einem Beleg gehört.
 *
 * Anders als beim Dubletten-Vergleich ist die Zuordnung hier also belegt und nicht
 * geraten: der Satz „RE-4711, Belegdatum 01.03.2026, bezahlt 28.03.2026" gehört zu
 * dem Beleg, dessen Schlüssel in der Referenz steht. Zerlegt wird er trotzdem nur
 * dann, wenn er sich bei **jedem** Beleg zerlegen lässt (`parseDocumentFacts`) –
 * sonst stünde auf einer Karte ein Feldraster und auf der anderen ein Satz.
 *
 * Der Betrag je Beleg steht in keinem Feld. Er wird benannt, nicht aus
 * `current.display` oder `impact_eur` herausgelesen: „32.000,00 €" ist die
 * Euro-Wirkung des Findings, nicht nachweislich der Betrag jedes einzelnen Belegs
 * (CLAUDE.md, Regel 4). Die Schema-Rückmeldung dazu heißt `entity.documents[].amount`.
 */

import type { Evidence, Finding, FindingDocument } from '@/types/finding'

/** Kartenfelder der Spec, in ihrer Reihenfolge. */
export const DOCUMENT_FIELDS = ['Belegnummer', 'Referenz', 'Belegdatum', 'Betrag'] as const

/** Beschriftung, wenn sich der Evidenztext nicht in Felder zerlegen lässt. */
export const RAW_FACT_LABEL = 'Angabe'

export interface DocumentFacts {
  /** Referenz des Belegs, z. B. `RE-4711` (XBLNR). */
  reference: string
  /** Belegdatum, bereits deutsch formatiert – so steht es im Quelltext. */
  documentDate: string
  /** Ausgleichsdatum („bezahlt am"). */
  clearedOn: string
}

export interface DocumentCard {
  /** `BUKRS/GJAHR/BELNR` – die Belegnummer, wie sie in SAP angesprochen wird. */
  key: string
  document: FindingDocument
  /** Zerlegte Felder, oder `null` – dann gilt `raw`. */
  facts: DocumentFacts | null
  /** Evidenztext wörtlich, wenn die Zerlegung nicht trägt. */
  raw: string | null
  /** Die zum Beleg gehörende Evidenz – für Datum und Notiz der Karte. */
  evidence: Evidence
}

export interface DocumentPair {
  cards: DocumentCard[]
  /** Fuzzy-Grund: warum hält die Engine die beiden für dasselbe (`source_summary`). */
  fuzzyReason: string | null
  /** Netting-Nachweis: die Evidenz, die nach einer Gutschrift gesucht hat. */
  netting: Evidence | null
  /** Kartenfelder der Spec, die das Finding nicht hergibt. */
  missingFields: string[]
}

/** Belegschlüssel wie in der Evidenz-Referenz: `1000/2026/1900004411`. */
export function documentKey(document: FindingDocument): string {
  return `${document.company_code}/${document.fiscal_year}/${document.document_no}`
}

/**
 * Die Evidenz zu einem Beleg, oder `null`.
 *
 * Erst der volle Schlüssel, dann die Belegnummer als **ganzes** Segment der Referenz –
 * eine Teilzeichenkette würde `1900004411` auch in `11900004411` finden.
 */
export function evidenceForDocument(
  evidence: readonly Evidence[],
  document: FindingDocument,
): Evidence | null {
  const key = documentKey(document)
  const exact = evidence.find((entry) => entry.reference.trim() === key)
  if (exact) return exact

  const segments = (entry: Evidence) => entry.reference.split(/[^0-9A-Za-z-]+/)
  const found = evidence.find((entry) => segments(entry).includes(document.document_no.trim()))
  return found ?? null
}

/**
 * Zerlegt „<Referenz>, Belegdatum <TT.MM.JJJJ>, bezahlt <TT.MM.JJJJ>".
 * `null`, sobald der Satz anders gebaut ist – dann steht er wörtlich da.
 */
export function parseDocumentFacts(value: string | null | undefined): DocumentFacts | null {
  if (value == null) return null
  const match = value
    .trim()
    .match(/^(.+?),\s*Belegdatum\s+(\d{2}\.\d{2}\.\d{4}),\s*bezahlt\s+(\d{2}\.\d{2}\.\d{4})$/)
  if (!match) return null
  const reference = match[1].trim()
  if (reference === '') return null
  return { reference, documentDate: match[2], clearedOn: match[3] }
}

/**
 * Der Netting-Nachweis: die Evidenz, deren Notiz die Netting-Prüfung benennt.
 *
 * Erkennung am Wort in einem Freitextfeld – als Übergang abgestimmt (Freigabe Victor).
 * Die Rückmeldung ans Schema heißt `evidence.reference_kind: netting`; bis dahin darf
 * eine andere Formulierung dazu führen, dass der Nachweis nur im Evidenz-Panel steht.
 */
export function nettingEvidence(evidence: readonly Evidence[]): Evidence | null {
  return evidence.find((entry) => /netting/i.test(entry.note ?? '')) ?? null
}

/**
 * Die ganze Belegpaar-Ansicht, oder `null`, wenn die Daten sie nicht tragen.
 *
 * `null` heißt: die Karte sieht aus wie jede andere. Bedingungen: `leakage`,
 * mindestens zwei Belege, und zu **jedem** Beleg eine zuordenbare Evidenz. Fehlt zu
 * einem die Evidenz, wäre die Karte leer bis auf den Schlüssel – zwei halbe Karten
 * sind schlechter als der gewohnte Abschnitt.
 */
export function buildDocumentPair(finding: Finding): DocumentPair | null {
  if (finding.category !== 'leakage') return null

  const documents = finding.entity.documents ?? []
  if (documents.length < 2) return null

  const evidence = finding.evidence ?? []
  const matched = documents.map((document) => evidenceForDocument(evidence, document))
  if (matched.some((entry) => entry == null)) return null
  const entries = matched as Evidence[]

  // Alles oder nichts: nur wenn sich jeder Text zerlegen lässt, entstehen Feldraster.
  const parsed = entries.map((entry) => parseDocumentFacts(entry.value))
  const structured = parsed.every((facts) => facts != null)

  const cards: DocumentCard[] = documents.map((document, index) => ({
    key: documentKey(document),
    document,
    facts: structured ? parsed[index] : null,
    raw: structured ? null : (entries[index].value?.trim() ?? null),
    evidence: entries[index],
  }))

  // „Belegnummer" steht immer, sie ist der Schlüssel. „Betrag" fehlt immer – er steht
  // in keinem Feld je Beleg. Referenz und Belegdatum nur, wenn die Zerlegung trug.
  const covered = new Set<string>(['Belegnummer'])
  if (structured) {
    covered.add('Referenz')
    covered.add('Belegdatum')
  }
  const missingFields = DOCUMENT_FIELDS.filter((field) => !covered.has(field))

  const summary = finding.proposed?.source_summary?.trim()

  return {
    cards,
    fuzzyReason: summary == null || summary === '' ? null : summary,
    netting: nettingEvidence(evidence),
    missingFields,
  }
}
