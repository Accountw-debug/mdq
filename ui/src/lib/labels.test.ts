import { describe, expect, it } from 'vitest'
import {
  ACTION_TYPE_LABELS,
  CATEGORY_LABELS,
  DAMAGE_CLASS_LABELS,
  ROLE_LABELS,
  SEVERITY_LABELS,
  SIDE_LABELS,
  SIDE_SHORT_LABELS,
  SOURCE_TYPE_LABELS,
  STATUS_LABELS,
  TIER_LABELS,
  TIER_SHORT_LABELS,
} from '@/lib/labels'
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
} from '@/types/finding'

/**
 * Driftschutz: Wächst eine Enum-Liste im Schema, fehlt hier sofort eine
 * Beschriftung – statt dass im UI irgendwo `undefined` steht.
 */
const MAPS: [string, readonly (string | number)[], Record<string | number, string>][] = [
  ['Seite', SIDES, SIDE_LABELS],
  ['Seite (kurz)', SIDES, SIDE_SHORT_LABELS],
  ['Kategorie', CATEGORIES, CATEGORY_LABELS],
  ['Schwere', SEVERITIES, SEVERITY_LABELS],
  ['Schadensklasse', DAMAGE_CLASSES, DAMAGE_CLASS_LABELS],
  ['Stufe', TIERS, TIER_LABELS],
  ['Stufe (kurz)', TIERS, TIER_SHORT_LABELS],
  ['Aktionstyp', ACTION_TYPES, ACTION_TYPE_LABELS],
  ['Status', STATUSES, STATUS_LABELS],
  ['Rolle', ROLES, ROLE_LABELS],
  ['Quellentyp', SOURCE_TYPES, SOURCE_TYPE_LABELS],
]

describe('Beschriftungen', () => {
  it.each(MAPS)('%s: jeder Wert hat genau eine Beschriftung', (_name, values, labels) => {
    expect(Object.keys(labels).sort()).toEqual([...values].map(String).sort())
    for (const value of values) {
      expect(labels[value]).toBeTruthy()
    }
  })

  it('nennt die Kategorien wie docs/CONCEPT.md, Abschnitt 3', () => {
    expect(CATEGORY_LABELS.completeness).toBe('Vollständigkeit')
    expect(CATEGORY_LABELS.validity).toBe('Validität')
    expect(CATEGORY_LABELS.consistency).toBe('Konsistenz')
  })
})
