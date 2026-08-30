/**
 * Rauchtest: rendert den Explorer mit den sechs Beispiel-Findings zu HTML.
 *
 * Kein DOM und keine Testing Library – `renderToStaticMarkup` läuft in der
 * Node-Umgebung und beantwortet genau die Frage, die Typprüfung und Reducer-Tests
 * offenlassen: kommen Zeilen, Beträge und Zähler tatsächlich am Bildschirm an.
 */
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { load as loadYaml } from 'js-yaml'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { FindingsExplorer } from '@/components/explorer/FindingsExplorer'
import { TooltipProvider } from '@/components/ui/tooltip'
import type { DecisionsState } from '@/state/decisions'
import { NO_DECISIONS, applyDecisions } from '@/state/decisions'
import type { ExplorerState } from '@/state/explorer'
import { INITIAL_EXPLORER_STATE } from '@/state/explorer'
import type { ActionType, Finding } from '@/types/finding'

const EXAMPLES_DIR = fileURLToPath(new URL('../../../../logic/examples/findings', import.meta.url))

const examples: Finding[] = readdirSync(EXAMPLES_DIR)
  .filter((name) => name.endsWith('.yaml'))
  .sort()
  .map((name) => loadYaml(readFileSync(join(EXAMPLES_DIR, name), 'utf8')) as Finding)

function render(state: Partial<ExplorerState> = {}, decisions: DecisionsState = NO_DECISIONS): string {
  return renderToStaticMarkup(
    <TooltipProvider>
      <FindingsExplorer
        findings={applyDecisions(examples, decisions)}
        decisions={decisions}
        reviewer="V. Test"
        state={{ ...INITIAL_EXPLORER_STATE, ...state }}
        dispatch={() => {}}
        onDecide={() => {}}
        onClearDecision={() => {}}
      />
    </TooltipProvider>,
  )
}

/** Zählt Tabellenzeilen ohne Kopfzeile. */
function rowCount(html: string): number {
  return (html.match(/<tr /g) ?? []).length - 1
}

describe('Explorer im Browser-Markup', () => {
  it('zeigt im Tab Review vier Zeilen mit deutschen Beträgen', () => {
    const html = render()
    expect(rowCount(html)).toBe(4)
    expect(html).toContain('32.000,00 €')
    expect(html).toContain('27.300,00 €')
    expect(html).toContain('AP-LEA-001')
  })

  it('zeigt je Tab die Findings dieses Aktionstyps', () => {
    expect(rowCount(render({ tab: 'decision' }))).toBe(1)
    expect(render({ tab: 'decision' })).toContain('8.930,00 €')
    expect(rowCount(render({ tab: 'process' }))).toBe(1)
    expect(render({ tab: 'process' })).toContain('4.812,40 €')
  })

  it('erklärt den leeren Tab Massenänderung, statt eine leere Tabelle zu zeigen', () => {
    const html = render({ tab: 'mass_change' as ActionType })
    expect(html).not.toContain('<table')
    expect(html).toContain('Stufe A')
  })

  it('blendet mit einem Filter aus und erklärt den Leerzustand', () => {
    const gefiltert = render({ filters: { ...INITIAL_EXPLORER_STATE.filters, side: 'AP' } })
    expect(rowCount(gefiltert)).toBe(2)
    const leer = render({ filters: { ...INITIAL_EXPLORER_STATE.filters, severity: 'low' } })
    expect(leer).toContain('Keine Findings mit diesen Filtern')
  })

  it('hebt die Auswahl hervor', () => {
    const html = render({ selectedId: 'F-c41d7e9b2a60' })
    expect(html).toContain('data-selected="true"')
  })

  it('nennt den Tastaturweg unter der Tabelle', () => {
    const html = render()
    expect(html).toContain('nächstes bzw. voriges Finding')
    expect(html).toContain('übernehmen')
  })

  it('zeigt in der Statusspalte, was mit dem Finding geschehen ist', () => {
    const html = render(
      {},
      {
        'F-c41d7e9b2a60': {
          finding_id: 'F-c41d7e9b2a60',
          action: 'accept',
          reason_code: null,
          reason: 'Vorschlag übernommen',
          assigned_to: null,
          by: 'V. Test',
          at: '2026-08-30T10:00:00.000Z',
        },
      },
    )
    expect(html).toContain('freigegeben – Umsetzung offen')
    // Die übrigen Zeilen bleiben offen.
    expect(html).toContain('>offen<')
  })

  // Der Drawer hängt in einem Portal; `renderToStaticMarkup` kennt keine Portale und
  // gibt seinen Inhalt nicht aus. Die Karte selbst prüft `ReviewCard.render.test.tsx`,
  // die dafür ohne Portal auskommt.
  it('rendert auch mit offenem Drawer fehlerfrei', () => {
    expect(() => render({ selectedId: 'F-c41d7e9b2a60', drawerOpen: true })).not.toThrow()
  })
})
