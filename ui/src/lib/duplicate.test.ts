/** Dubletten-Vergleich: Kontenzuordnung, Zeilen, Match-Chips, führendes Konto. */
import { describe, expect, it } from 'vitest'
import {
  RAW_ROW_LABEL,
  SPEC_FIELDS,
  accountMatches,
  buildDuplicateComparison,
  duplicateAccounts,
  matchReasons,
  normalizeAccount,
} from '@/lib/duplicate'
import type { Finding } from '@/types/finding'

/** Gerüst eines Dubletten-Findings nach dem Muster von F-7b2e8c1d9a3f. */
function finding(overrides: Partial<Finding> = {}): Finding {
  return {
    finding_id: 'F-000000000002',
    run_id: 'demo',
    rule_id: 'AR-DUP-001',
    rule_version: '1.0',
    engine_version: '0.1.0',
    pack_version: '0.1',
    side: 'AR',
    category: 'duplicate',
    severity: 'high',
    damage_class: 2,
    tier: 'B',
    action_type: 'review',
    title: 'Mögliche Dublette im Debitorenstamm',
    entity: {
      bp_key: 'C:0000100234',
      role: 'CUSTOMER',
      related_bp_keys: ['C:0000100987'],
    },
    current: {
      source_table: 'KNA1',
      source_field: 'KUNNR',
      value: '0000100234 | 0000100987',
      display:
        'Müller Maschinenbau GmbH, Robert-Bosch-Str. 12, 86159 Augsburg | Mueller Maschinenbau GmbH, Robert Bosch Straße 12, 86159 Augsburg',
    },
    proposed: {
      value: '0000100234',
      display: 'Führendes Konto 0000100234; 0000100987 sperren',
      source_summary: 'Name und Straße nach Normalisierung identisch',
    },
    evidence: [
      {
        source_type: 'model',
        reference: 'cluster-000412',
        value: 'name_norm gleich, street_norm gleich, postal_code gleich',
        observed_at: null,
        agrees: true,
        note: 'Match-Gründe: Mueller→Müller (Transliteration)',
      },
    ],
    why: 'Grund für den Test.',
    if_wrong: 'Folge im Test.',
    remediation: { sap_transaction: 'XD05', mass_change_eligible: false },
    status: 'open',
    data_as_of: '2026-08-28',
    created_at: '2026-08-30T09:15:00Z',
    ...overrides,
  }
}

describe('normalizeAccount / accountMatches', () => {
  it('streift Rollenpräfix und führende Nullen ab', () => {
    expect(normalizeAccount('C:0000100234')).toBe('100234')
    expect(normalizeAccount('0000100234')).toBe('100234')
    expect(normalizeAccount('V:0000200001')).toBe('200001')
  })

  it('erkennt dasselbe Konto mit und ohne Präfix', () => {
    expect(accountMatches('C:0000100234', '0000100234')).toBe(true)
    expect(accountMatches('C:0000100234', '100234')).toBe(true)
    expect(accountMatches('C:0000100234', 'C:0000100234')).toBe(true)
  })

  it('verwechselt verschiedene Konten nicht und stolpert nicht über Leeres', () => {
    expect(accountMatches('C:0000100234', '0000100987')).toBe(false)
    expect(accountMatches('C:0000100234', null)).toBe(false)
    expect(accountMatches('C:0000100234', '  ')).toBe(false)
  })

  it('macht aus lauter Nullen keine leere Zeichenkette', () => {
    expect(normalizeAccount('0000000000')).toBe('0')
  })
})

describe('duplicateAccounts', () => {
  it('nennt das Finding-Konto zuerst, dann die verwandten', () => {
    expect(duplicateAccounts(finding())).toEqual(['C:0000100234', 'C:0000100987'])
  })

  it('führt jedes Konto nur einmal', () => {
    const doubled = finding({
      entity: {
        bp_key: 'C:0000100234',
        role: 'CUSTOMER',
        related_bp_keys: ['C:0000100987', 'C:0000100234'],
      },
    })
    expect(duplicateAccounts(doubled)).toEqual(['C:0000100234', 'C:0000100987'])
  })
})

describe('matchReasons', () => {
  it('macht aus der Evidenz mit source_type model drei Chips', () => {
    const { chips, note } = matchReasons(finding().evidence ?? [])
    expect(chips).toEqual(['name_norm gleich', 'street_norm gleich', 'postal_code gleich'])
    expect(note).toBe('Match-Gründe: Mueller→Müller (Transliteration)')
  })

  it('nimmt nur Modell-Evidenz, nicht jede', () => {
    const { chips } = matchReasons([
      {
        source_type: 'deterministic',
        reference: 'KNVP',
        value: 'kein RG/RE-Bezug',
        observed_at: null,
        agrees: true,
      },
    ])
    expect(chips).toEqual([])
  })
})

describe('buildDuplicateComparison', () => {
  it('baut zwei Spalten und setzt die Krone auf das führende Konto', () => {
    const comparison = buildDuplicateComparison(finding())
    expect(comparison?.accounts).toEqual([
      { bpKey: 'C:0000100234', isLead: true },
      { bpKey: 'C:0000100987', isLead: false },
    ])
  })

  it('zerlegt die Adresszeile in Name, Straße und PLZ/Ort', () => {
    const rows = buildDuplicateComparison(finding())?.rows ?? []
    expect(rows.map((row) => row.label)).toEqual(['Name', 'Straße', 'PLZ/Ort'])
    expect(rows[0].cells).toEqual(['Müller Maschinenbau GmbH', 'Mueller Maschinenbau GmbH'])
    expect(rows[2].cells).toEqual(['86159 Augsburg', '86159 Augsburg'])
  })

  it('hebt Name und Straße hervor, die gleiche PLZ/Ort-Zeile nicht', () => {
    const rows = buildDuplicateComparison(finding())?.rows ?? []
    expect(rows.map((row) => row.differs)).toEqual([true, true, false])
  })

  it('benennt die sechs Felder, die das Finding nicht hergibt', () => {
    const comparison = buildDuplicateComparison(finding())
    expect(comparison?.missingFields).toEqual([
      'Land',
      'USt-ID',
      'IBAN',
      'Zahlungsbedingung',
      'Offene Posten',
      'Letzte Zahlung',
    ])
  })

  it('ordnet die Spalten über den Schlüssel zu, nicht über die Position', () => {
    const swapped = finding({
      current: {
        source_table: 'KNA1',
        source_field: 'KUNNR',
        value: '0000100987 | 0000100234',
        display: 'Zweitkonto, Weg 2, 86159 Augsburg | Erstkonto, Weg 1, 86159 Augsburg',
      },
    })
    const rows = buildDuplicateComparison(swapped)?.rows ?? []
    expect(rows[0].cells).toEqual(['Erstkonto', 'Zweitkonto'])
  })

  it('zeigt die Zeile wörtlich, wenn sie sich nicht in drei Teile zerlegen lässt', () => {
    const odd = finding({
      current: {
        source_table: 'KNA1',
        source_field: 'KUNNR',
        value: '0000100234 | 0000100987',
        display: 'Müller Maschinenbau GmbH | Mueller Maschinenbau GmbH, Weg 1, 86159 Augsburg',
      },
    })
    const comparison = buildDuplicateComparison(odd)
    expect(comparison?.rows.map((row) => row.label)).toEqual([RAW_ROW_LABEL])
    expect(comparison?.rows[0].cells[0]).toBe('Müller Maschinenbau GmbH')
    // Ohne benannte Zeilen fehlt die ganze Feldliste der Spec.
    expect(comparison?.missingFields).toEqual([...SPEC_FIELDS])
  })

  it('gibt null zurück, wenn die Segmentzahl nicht zu den Konten passt', () => {
    const short = finding({
      current: {
        source_table: 'KNA1',
        source_field: 'KUNNR',
        value: '0000100234',
        display: 'Müller Maschinenbau GmbH, Weg 1, 86159 Augsburg',
      },
    })
    expect(buildDuplicateComparison(short)).toBeNull()
  })

  it('gibt null zurück, wenn ein Segment zu keinem Konto gehört', () => {
    const foreign = finding({
      current: {
        source_table: 'KNA1',
        source_field: 'KUNNR',
        value: '0000100234 | 0000999999',
        display: 'A, Weg 1, 86159 Augsburg | B, Weg 2, 86159 Augsburg',
      },
    })
    expect(buildDuplicateComparison(foreign)).toBeNull()
  })

  it('gibt null zurück, wenn es kein zweites Konto gibt', () => {
    const alone = finding({ entity: { bp_key: 'C:0000100234', role: 'CUSTOMER' } })
    expect(buildDuplicateComparison(alone)).toBeNull()
  })

  it('bleibt bei fehlendem current.display bei Spalten ohne Zeilen', () => {
    const noDisplay = finding({
      current: {
        source_table: 'KNA1',
        source_field: 'KUNNR',
        value: '0000100234 | 0000100987',
        display: null,
      },
    })
    const comparison = buildDuplicateComparison(noDisplay)
    expect(comparison?.accounts).toHaveLength(2)
    expect(comparison?.rows).toEqual([])
    expect(comparison?.missingFields).toEqual([...SPEC_FIELDS])
  })

  it('setzt keine Krone, wenn proposed.value auf kein Konto zeigt', () => {
    const unclear = finding({
      proposed: { value: null, display: null, source_summary: 'offen' },
    })
    expect(buildDuplicateComparison(unclear)?.accounts.every((a) => !a.isLead)).toBe(true)
  })
})
