/**
 * Driftschutz für `finding.ts`: die Enum-Listen sind eine Kopie aus
 * `logic/finding.schema.json`. Ändert die Engine-Session dort einen Wert,
 * schlägt dieser Test fehl, statt dass das UI still einen Fall verschluckt.
 *
 * Das Schema wird nur gelesen – geschrieben wird in diesem Branch ausschließlich
 * unter `ui/` (ui/NOTES.md, Arbeitsvereinbarung).
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import {
  ACTION_TYPES,
  CATEGORIES,
  DAMAGE_CLASSES,
  ROLES,
  SEVERITIES,
  SIDES,
  REFERENCE_KINDS,
  SOURCE_TYPES,
  STATUSES,
  TIERS,
} from './finding'

const SCHEMA_PATH = fileURLToPath(new URL('../../../logic/finding.schema.json', import.meta.url))
const schema = JSON.parse(readFileSync(SCHEMA_PATH, 'utf8'))

/**
 * Löst `{"$ref": "#/$defs/..."}` auf. Seit Schema 1.1 stehen die Wiederholungen
 * unter `$defs` (D-069, Punkt 7); ohne das hier liefe der Pfad ins Leere und der
 * Driftschutz meldete einen Schema-Umbau als fehlendes Feld.
 */
function deref(node: unknown): unknown {
  let current = node
  const seen = new Set<string>()
  while (typeof current === 'object' && current !== null && '$ref' in current) {
    const ref = (current as { $ref: unknown }).$ref
    if (typeof ref !== 'string' || !ref.startsWith('#/')) {
      throw new Error(`Nicht auflösbarer $ref: ${JSON.stringify(ref)}`)
    }
    if (seen.has(ref)) throw new Error(`$ref im Kreis: ${ref}`)
    seen.add(ref)
    current = at(ref.slice(2).split('/'))
  }
  return current
}

/** Folgt einem Pfad wie ["properties", "side", "enum"] und wirft, wenn er ins Leere läuft. */
function at(path: readonly string[]): unknown {
  let node: unknown = schema
  const walked: string[] = []
  for (const segment of path) {
    walked.push(segment)
    node = deref(node)
    if (typeof node !== 'object' || node === null || !(segment in node)) {
      throw new Error(`Pfad im Schema nicht gefunden: ${walked.join('.')}`)
    }
    node = (node as Record<string, unknown>)[segment]
  }
  return deref(node)
}

const CASES: ReadonlyArray<[string, readonly string[], readonly (string | number)[]]> = [
  ['side', ['properties', 'side', 'enum'], SIDES],
  ['category', ['properties', 'category', 'enum'], CATEGORIES],
  ['severity', ['properties', 'severity', 'enum'], SEVERITIES],
  ['damage_class', ['properties', 'damage_class', 'enum'], DAMAGE_CLASSES],
  ['tier', ['properties', 'tier', 'enum'], TIERS],
  ['action_type', ['properties', 'action_type', 'enum'], ACTION_TYPES],
  ['entity.role', ['properties', 'entity', 'properties', 'role', 'enum'], ROLES],
  [
    'evidence[].source_type',
    ['properties', 'evidence', 'items', 'properties', 'source_type', 'enum'],
    SOURCE_TYPES,
  ],
  [
    'evidence[].reference_kind',
    ['properties', 'evidence', 'items', 'properties', 'reference_kind', 'enum'],
    REFERENCE_KINDS,
  ],
  ['status', ['properties', 'status', 'enum'], STATUSES],
]

describe('Enum-Abgleich mit logic/finding.schema.json', () => {
  it.each(CASES)('%s deckt sich mit dem Schema', (_name, path, values) => {
    expect(at(path)).toEqual([...values])
  })

  it('kennt alle Pflichtfelder des Schemas', () => {
    // Reine Kontrolle, dass der Pfad stimmt und das Schema geladen wurde.
    expect(at(['required'])).toContain('finding_id')
    expect(at(['title'])).toBe('MDQ Finding')
  })

  it('liest die Schema-Version, gegen die `finding.ts` geschrieben ist', () => {
    // Kein Finding trägt eine Schema-Version; sie steht als Metaschlüssel am
    // Vertrag (D-069, Punkt 1). Steigt sie, gehört `finding.ts` durchgesehen.
    expect(at(['version'])).toBe('1.1')
  })

  it('führt `title` als Pflichtfeld – die Findings-Liste braucht eine Spalte', () => {
    expect(at(['required'])).toContain('title')
  })

  it('kennt die Felder aus D-069', () => {
    const documentFields = at(['properties', 'entity', 'properties', 'documents', 'items', 'properties'])
    expect(Object.keys(documentFields as object)).toEqual([
      'company_code',
      'fiscal_year',
      'document_no',
      'line_item',
      'reference',
      'document_date',
      'cleared_on',
      'amount',
      'currency',
    ])

    // `entity.records[].fields` und `proposed.golden_record` müssen dieselben
    // Feldnamen führen – sonst zeigt die Vergleichstabelle einen Zielwert für
    // ein Feld, das es in der Zeile nicht gibt (D-069, Punkt 6).
    const recordFields = Object.keys(
      at(['properties', 'entity', 'properties', 'records', 'items', 'properties', 'fields', 'properties']) as object,
    )
    const goldenRecordFields = Object.keys(
      at(['properties', 'proposed', 'properties', 'golden_record', 'properties']) as object,
    )
    expect(goldenRecordFields).toEqual(recordFields)

    expect(at(['properties', 'decision', 'properties', 'assigned_to', 'type'])).toBe('string')
  })
})
