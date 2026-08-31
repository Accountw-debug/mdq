/** Belegpaar-Ansicht: Belegschlüssel, Zuordnung der Evidenz, Zerlegung, Netting. */
import { describe, expect, it } from 'vitest'
import {
  DOCUMENT_FIELDS,
  buildDocumentPair,
  documentKey,
  evidenceForDocument,
  nettingEvidence,
  parseDocumentFacts,
} from '@/lib/documents'
import type { Finding } from '@/types/finding'

/** Gerüst eines Doppelzahlungs-Findings nach dem Muster von F-c41d7e9b2a60. */
function finding(overrides: Partial<Finding> = {}): Finding {
  return {
    finding_id: 'F-000000000003',
    run_id: 'demo',
    rule_id: 'AP-LEA-001',
    rule_version: '1.0',
    engine_version: '0.1.0',
    pack_version: '0.1',
    side: 'AP',
    category: 'leakage',
    severity: 'critical',
    damage_class: 2,
    tier: 'B',
    action_type: 'review',
    title: 'Mögliche Doppelzahlung',
    entity: {
      bp_key: 'V:0000200845',
      role: 'VENDOR',
      company_code: '1000',
      documents: [
        { company_code: '1000', fiscal_year: '2026', document_no: '1900004411', line_item: '001' },
        { company_code: '1000', fiscal_year: '2026', document_no: '1900004587', line_item: '001' },
      ],
    },
    current: {
      source_table: 'BSAK',
      source_field: 'XBLNR',
      value: 'RE-4711 | RE4711',
      display: 'Zwei bezahlte Rechnungen über 32.000,00 EUR',
    },
    proposed: {
      value: null,
      display: 'Rückforderung an Lieferant oder Verrechnung mit nächster Rechnung',
      source_summary: 'Belegpaar: gleicher Betrag, Referenz nahezu identisch, 9 Tage Abstand',
    },
    evidence: [
      {
        source_type: 'deterministic',
        reference: '1000/2026/1900004411',
        value: 'RE-4711, Belegdatum 01.03.2026, bezahlt 28.03.2026',
        observed_at: '2026-03-01',
        agrees: true,
        note: 'Rechnung A',
      },
      {
        source_type: 'deterministic',
        reference: '1000/2026/1900004587',
        value: 'RE4711, Belegdatum 10.03.2026, bezahlt 09.04.2026',
        observed_at: '2026-03-10',
        agrees: true,
        note: 'Rechnung B – Referenz ohne Bindestrich erfasst',
      },
      {
        source_type: 'deterministic',
        reference: 'BSAK Gutschriften 10.03.–06.09.2026',
        value: 'keine Gutschrift über 32.000,00 EUR',
        observed_at: '2026-08-28',
        agrees: true,
        note: 'Netting-Prüfung',
      },
    ],
    why: 'Grund für den Test.',
    if_wrong: 'Folge im Test.',
    remediation: { sap_transaction: 'FBL1N', mass_change_eligible: false },
    status: 'open',
    data_as_of: '2026-08-28',
    created_at: '2026-08-30T09:15:00Z',
    ...overrides,
  }
}

describe('documentKey / evidenceForDocument', () => {
  it('baut den Schlüssel wie die Evidenz-Referenz', () => {
    expect(
      documentKey({ company_code: '1000', fiscal_year: '2026', document_no: '1900004411' }),
    ).toBe('1000/2026/1900004411')
  })

  it('findet die Evidenz über den vollen Schlüssel', () => {
    const example = finding()
    const entry = evidenceForDocument(example.evidence ?? [], example.entity.documents![0])
    expect(entry?.note).toBe('Rechnung A')
  })

  it('findet sie auch, wenn die Referenz nur die Belegnummer nennt', () => {
    const example = finding({
      evidence: [
        {
          source_type: 'deterministic',
          reference: 'Beleg 1900004411',
          value: 'RE-4711',
          observed_at: null,
          agrees: true,
          note: null,
        },
      ],
    })
    const entry = evidenceForDocument(example.evidence ?? [], example.entity.documents![0])
    expect(entry?.value).toBe('RE-4711')
  })

  it('verwechselt keine Belegnummer, die nur zufällig enthalten ist', () => {
    const example = finding({
      evidence: [
        {
          source_type: 'deterministic',
          reference: '1000/2026/11900004411',
          value: 'anderer Beleg',
          observed_at: null,
          agrees: true,
          note: null,
        },
      ],
    })
    expect(evidenceForDocument(example.evidence ?? [], example.entity.documents![0])).toBeNull()
  })
})

describe('parseDocumentFacts', () => {
  it('zerlegt Referenz, Belegdatum und Zahldatum', () => {
    expect(parseDocumentFacts('RE-4711, Belegdatum 01.03.2026, bezahlt 28.03.2026')).toEqual({
      reference: 'RE-4711',
      documentDate: '01.03.2026',
      clearedOn: '28.03.2026',
    })
  })

  it('gibt null zurück, wenn der Satz anders gebaut ist', () => {
    expect(parseDocumentFacts('RE-4711 vom 01.03.2026')).toBeNull()
    expect(parseDocumentFacts('Belegdatum 01.03.2026, bezahlt 28.03.2026')).toBeNull()
    expect(parseDocumentFacts(null)).toBeNull()
  })
})

describe('nettingEvidence', () => {
  it('erkennt die Netting-Prüfung an der Notiz', () => {
    const entry = nettingEvidence(finding().evidence ?? [])
    expect(entry?.reference).toContain('Gutschriften')
  })

  it('findet nichts, wenn die Notiz das Wort nicht nennt', () => {
    const entries = (finding().evidence ?? []).map((entry) => ({ ...entry, note: 'Hinweis' }))
    expect(nettingEvidence(entries)).toBeNull()
  })
})

describe('buildDocumentPair', () => {
  it('baut zwei Karten mit zerlegten Feldern, Fuzzy-Grund und Netting-Nachweis', () => {
    const pair = buildDocumentPair(finding())
    expect(pair).not.toBeNull()
    expect(pair!.cards.map((card) => card.key)).toEqual([
      '1000/2026/1900004411',
      '1000/2026/1900004587',
    ])
    expect(pair!.cards[1].facts?.reference).toBe('RE4711')
    expect(pair!.cards[1].facts?.clearedOn).toBe('09.04.2026')
    expect(pair!.fuzzyReason).toContain('9 Tage Abstand')
    expect(pair!.netting?.note).toBe('Netting-Prüfung')
  })

  it('nennt den Betrag als fehlendes Feld, die Belegnummer nicht', () => {
    const pair = buildDocumentPair(finding())
    expect(pair!.missingFields).toEqual(['Betrag'])
    expect(DOCUMENT_FIELDS).toContain('Betrag')
  })

  it('zerlegt alles oder nichts – ein abweichender Satz lässt beide Karten wörtlich', () => {
    const example = finding()
    const evidence = [...(example.evidence ?? [])]
    evidence[1] = { ...evidence[1], value: 'RE4711, gebucht am 10.03.2026' }
    const pair = buildDocumentPair(finding({ evidence }))
    expect(pair!.cards.every((card) => card.facts == null)).toBe(true)
    expect(pair!.cards[0].raw).toBe('RE-4711, Belegdatum 01.03.2026, bezahlt 28.03.2026')
    expect(pair!.missingFields).toEqual(['Referenz', 'Belegdatum', 'Betrag'])
  })

  it('gibt null zurück ohne Belege, mit nur einem Beleg und außerhalb von leakage', () => {
    expect(buildDocumentPair(finding({ entity: { bp_key: 'V:1', role: 'VENDOR' } }))).toBeNull()
    expect(
      buildDocumentPair(
        finding({
          entity: {
            bp_key: 'V:1',
            role: 'VENDOR',
            documents: [
              { company_code: '1000', fiscal_year: '2026', document_no: '1900004411' },
            ],
          },
        }),
      ),
    ).toBeNull()
    expect(buildDocumentPair(finding({ category: 'validity' }))).toBeNull()
  })

  it('gibt null zurück, wenn zu einem Beleg keine Evidenz gehört', () => {
    const evidence = (finding().evidence ?? []).filter(
      (entry) => entry.reference !== '1000/2026/1900004587',
    )
    expect(buildDocumentPair(finding({ evidence }))).toBeNull()
  })
})
