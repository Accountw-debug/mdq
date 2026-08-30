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
  SOURCE_TYPES,
  STATUSES,
  TIERS,
} from './finding'

const SCHEMA_PATH = fileURLToPath(new URL('../../../logic/finding.schema.json', import.meta.url))
const schema = JSON.parse(readFileSync(SCHEMA_PATH, 'utf8'))

/** Folgt einem Pfad wie ["properties", "side", "enum"] und wirft, wenn er ins Leere läuft. */
function at(path: readonly string[]): unknown {
  let node: unknown = schema
  const walked: string[] = []
  for (const segment of path) {
    walked.push(segment)
    if (typeof node !== 'object' || node === null || !(segment in node)) {
      throw new Error(`Pfad im Schema nicht gefunden: ${walked.join('.')}`)
    }
    node = (node as Record<string, unknown>)[segment]
  }
  return node
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
})
