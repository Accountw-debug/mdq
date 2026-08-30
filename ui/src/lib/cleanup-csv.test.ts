/**
 * Bereinigungsliste als CSV (Aufgabe 7).
 *
 * Geprüft wird, was beim Öffnen in Excel schiefgehen könnte: Spaltenkopf, Trenner,
 * Umlaute, ein Semikolon im Wert. Dazu die Auswahl – die Liste ist eine
 * Arbeitsanweisung, keine Bestandsaufnahme.
 */
import { describe, expect, it } from 'vitest'
import {
  CLEANUP_COLUMNS,
  buildCleanupCsv,
  cleanupFileName,
  cleanupFindings,
} from '@/lib/cleanup-csv'
import type { DecisionsState } from '@/state/decisions'
import type { DecisionRecord } from '@/types/decision'
import type { Finding, RunInfo } from '@/types/finding'

const RUN: RunInfo = {
  run_id: 'demo-2026-08-30',
  data_as_of: '2026-08-28',
  engine_version: '0.1.0',
  pack_version: '0.1',
  tables_loaded: 0,
  company_codes: ['1000'],
}

function finding(id: string, overrides: Partial<Finding> = {}): Finding {
  return {
    finding_id: id,
    run_id: RUN.run_id,
    rule_id: 'AR-CMP-001',
    rule_version: '1.0',
    engine_version: '0.1.0',
    pack_version: '0.1',
    side: 'AR',
    category: 'completeness',
    severity: 'medium',
    damage_class: 3,
    tier: 'A',
    action_type: 'mass_change',
    entity: { bp_key: `C:${id}`, role: 'CUSTOMER', company_code: '1000' },
    current: { source_table: 'KNA1', source_field: 'STCEG', value: null },
    proposed: { value: 'DE123456789', source_summary: 'VIES bestätigt.' },
    why: 'Grund für den Test.',
    if_wrong: 'Folge im Test.',
    remediation: { sap_transaction: 'XD02', mass_change_eligible: true },
    status: 'open',
    data_as_of: '2026-08-28',
    created_at: '2026-08-30T09:15:00Z',
    ...overrides,
  }
}

function record(findingId: string, overrides: Partial<DecisionRecord> = {}): DecisionRecord {
  return {
    finding_id: findingId,
    action: 'accept',
    reason_code: null,
    reason: 'Vorschlag übernommen',
    assigned_to: null,
    by: 'V. Test',
    at: '2026-08-30T09:50:00.000Z',
    ...overrides,
  }
}

function decisions(...records: DecisionRecord[]): DecisionsState {
  return Object.fromEntries(records.map((entry) => [entry.finding_id, entry]))
}

/** Zerlegt eine CSV-Zeile so, wie ein Leser es täte: Trenner in Anführungszeichen trennen nicht. */
function fields(line: string): string[] {
  const out: string[] = []
  let current = ''
  let quoted = false
  for (let i = 0; i < line.length; i++) {
    const char = line[i]
    if (quoted) {
      if (char === '"' && line[i + 1] === '"') {
        current += '"'
        i += 1
      } else if (char === '"') quoted = false
      else current += char
    } else if (char === '"') quoted = true
    else if (char === ';') {
      out.push(current)
      current = ''
    } else current += char
  }
  out.push(current)
  return out
}

/** Zeilen ohne BOM und ohne die abschließende Leerzeile. */
function lines(csv: string): string[] {
  return csv.replace(/^﻿/, '').trimEnd().split('\r\n')
}

describe('cleanupFindings', () => {
  it('nimmt nur übernommene Massenänderungen', () => {
    const findings = [
      finding('F-1'),
      finding('F-2'),
      finding('F-3'),
      finding('F-4', { action_type: 'review' }),
    ]
    const stand = decisions(
      record('F-1'),
      record('F-2', { action: 'reject', reason_code: 'data_correct' }),
      record('F-4'),
    )
    expect(cleanupFindings(findings, stand).map((entry) => entry.finding_id)).toEqual(['F-1'])
  })

  it('sortiert nach Regel, dann Geschäftspartner (Regel 9)', () => {
    const findings = [
      finding('F-1', { rule_id: 'ZZ-XXX-001', entity: { bp_key: 'C:0002', role: 'CUSTOMER' } }),
      finding('F-2', { rule_id: 'AA-AAA-001', entity: { bp_key: 'C:0009', role: 'CUSTOMER' } }),
      finding('F-3', { rule_id: 'AA-AAA-001', entity: { bp_key: 'C:0001', role: 'CUSTOMER' } }),
    ]
    const stand = decisions(record('F-1'), record('F-2'), record('F-3'))
    expect(cleanupFindings(findings, stand).map((entry) => entry.finding_id)).toEqual([
      'F-3',
      'F-2',
      'F-1',
    ])
  })
})

describe('buildCleanupCsv', () => {
  it('schreibt den Spaltenkopf der Spec, mit Semikolon getrennt', () => {
    const csv = buildCleanupCsv([], {})
    expect(lines(csv)[0]).toBe(
      'bp_key;company_code;source_table;source_field;current;proposed;tier;rule_id',
    )
    expect(CLEANUP_COLUMNS).toHaveLength(8)
  })

  it('beginnt mit dem BOM und trennt Zeilen mit CRLF – sonst zerlegt Excel die Umlaute', () => {
    const csv = buildCleanupCsv([finding('F-1')], decisions(record('F-1')))
    expect(csv.startsWith('﻿')).toBe(true)
    expect(csv.endsWith('\r\n')).toBe(true)
    expect(csv).not.toContain('\n\n')
  })

  it('schreibt Ist und Soll unverändert und lässt leere Felder leer', () => {
    const csv = buildCleanupCsv([finding('F-1')], decisions(record('F-1')))
    expect(lines(csv)[1]).toBe('C:F-1;1000;KNA1;STCEG;;DE123456789;A;AR-CMP-001')
  })

  it('quotet Werte mit Semikolon, Anführungszeichen oder Zeilenumbruch', () => {
    const findings = [
      finding('F-1', {
        current: { source_table: 'KNA1', source_field: 'NAME1', value: 'Müller; Sohn' },
        proposed: { value: 'Sagt "Müller"', source_summary: 'Test.' },
      }),
    ]
    const zeile = lines(buildCleanupCsv(findings, decisions(record('F-1'))))[1]
    expect(zeile).toContain('"Müller; Sohn"')
    expect(zeile).toContain('"Sagt ""Müller"""')
    // Trotz Semikolon im Wert bleiben es acht Spalten mit den ursprünglichen Werten.
    expect(fields(zeile)).toHaveLength(8)
    expect(fields(zeile)[4]).toBe('Müller; Sohn')
    expect(fields(zeile)[5]).toBe('Sagt "Müller"')
  })

  it('lässt einen fehlenden Buchungskreis leer, statt ihn zu erfinden', () => {
    const ohne = finding('F-1', { entity: { bp_key: 'C:0001', role: 'CUSTOMER' } })
    expect(lines(buildCleanupCsv([ohne], decisions(record('F-1'))))[1]).toBe(
      'C:0001;;KNA1;STCEG;;DE123456789;A;AR-CMP-001',
    )
  })

  it('benennt die Datei nach dem Lauf', () => {
    expect(cleanupFileName(RUN)).toBe('bereinigungsliste-demo-2026-08-30.csv')
  })
})
