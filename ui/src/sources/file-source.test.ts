/**
 * Tests der Dateiquelle: `findings.json` und `run.json` eines Laufs werden
 * zusammen gewählt und an ihrem Inhalt unterschieden, nicht am Namen.
 */
import { describe, expect, it } from 'vitest'
import { fileSource } from '@/sources/file-source'
import { LoadError } from '@/sources/findings-source'

function jsonFile(name: string, value: unknown): File {
  return new File([JSON.stringify(value)], name, { type: 'application/json' })
}

const FINDING = {
  finding_id: 'F-000000000001',
  run_id: '2026-08-28-702323b8',
  rule_id: 'AR-VAL-001',
  rule_version: '1.0',
  engine_version: '0.1.0',
  pack_version: '0.1',
  side: 'AR',
  category: 'validity',
  severity: 'medium',
  damage_class: 3,
  tier: 'B',
  action_type: 'review',
  title: 'USt-IdNr. fehlt',
  entity: { bp_key: 'C:0000100001', role: 'CUSTOMER', company_code: '1000' },
  current: { source_table: 'KNA1', source_field: 'STCEG', value: null },
  why: 'warum',
  if_wrong: 'wenn falsch',
  remediation: { sap_transaction: 'XD02', mass_change_eligible: false },
  status: 'open',
  data_as_of: '2026-08-28',
  created_at: '2026-08-31T08:00:00Z',
}

const RUN = {
  run_id: '2026-08-28-702323b8',
  engine_version: '0.1.0',
  pack_version: '0.1',
  data_as_of: '2026-08-28',
  tables_loaded: 16,
  company_codes: ['1000', '2000'],
}

const findingsFile = () => jsonFile('findings.json', [FINDING])
const runFile = () => jsonFile('run.json', RUN)

describe('fileSource', () => {
  it('nimmt findings.json und run.json zusammen', async () => {
    const loaded = await fileSource([findingsFile(), runFile()]).loadRun()
    expect(loaded.findings).toHaveLength(1)
    expect(loaded.run.tables_loaded).toBe(16)
    expect(loaded.run.company_codes).toEqual(['1000', '2000'])
  })

  it('unterscheidet die Dateien am Inhalt, nicht am Namen', async () => {
    const loaded = await fileSource([
      jsonFile('b.json', RUN),
      jsonFile('a.json', { findings: [FINDING] }),
    ]).loadRun()
    expect(loaded.run.tables_loaded).toBe(16)
  })

  it('kommt ohne run.json aus – dann bleibt tables_loaded 0', async () => {
    const loaded = await fileSource([findingsFile()]).loadRun()
    expect(loaded.run.run_id).toBe('2026-08-28-702323b8')
    expect(loaded.run.tables_loaded).toBe(0)
  })

  it('nennt beide Dateien im Banner', () => {
    expect(fileSource([findingsFile(), runFile()]).label).toBe('findings.json + run.json')
  })

  it('meldet run.json ohne Findings-Datei', async () => {
    await expect(fileSource([runFile()]).loadRun()).rejects.toThrow(/Findings-Datei/)
  })

  it('meldet eine Datei, die weder das eine noch das andere ist', async () => {
    await expect(
      fileSource([findingsFile(), jsonFile('decisions.json', { format_version: 1 })]).loadRun(),
    ).rejects.toThrow(/decisions\.json/)
  })

  it('meldet zwei Findings-Dateien statt eine still zu übergehen', async () => {
    await expect(fileSource([findingsFile(), findingsFile()]).loadRun()).rejects.toThrow(
      /Mehr als eine Findings-Datei/,
    )
  })

  it('meldet zwei Lauf-Köpfe', async () => {
    await expect(fileSource([findingsFile(), runFile(), runFile()]).loadRun()).rejects.toThrow(
      /Mehr als eine run\.json/,
    )
  })

  it('meldet kaputtes JSON mit dem Dateinamen', async () => {
    const broken = new File(['{'], 'findings.json', { type: 'application/json' })
    await expect(fileSource([broken]).loadRun()).rejects.toThrow(/findings\.json/)
  })

  it('lehnt eine leere Auswahl ab', () => {
    expect(() => fileSource([])).toThrow(LoadError)
  })
})
