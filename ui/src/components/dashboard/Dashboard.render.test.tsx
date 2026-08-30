/**
 * Rauchtest: rendert das Dashboard mit den sechs Beispiel-Findings zu HTML.
 *
 * Wie beim Explorer ohne DOM und ohne Testing Library – `renderToStaticMarkup`
 * beantwortet die Frage, die die Reducer-Tests offenlassen: kommen die gerechneten
 * Zahlen in deutscher Schreibweise wirklich am Bildschirm an, und steht in der
 * Score-Kachel keine erfundene Kennzahl.
 */
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { load as loadYaml } from 'js-yaml'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { Dashboard } from '@/components/dashboard/Dashboard'
import { TooltipProvider } from '@/components/ui/tooltip'
import type { Finding } from '@/types/finding'

const EXAMPLES_DIR = fileURLToPath(new URL('../../../../logic/examples/findings', import.meta.url))

const examples: Finding[] = readdirSync(EXAMPLES_DIR)
  .filter((name) => name.endsWith('.yaml'))
  .sort()
  .map((name) => loadYaml(readFileSync(join(EXAMPLES_DIR, name), 'utf8')) as Finding)

function render(findings: readonly Finding[] = examples): string {
  return renderToStaticMarkup(
    <TooltipProvider>
      <Dashboard findings={findings} onOpenFinding={() => {}} />
    </TooltipProvider>,
  )
}

/** Zählt die Zeilen der Top-Liste. */
function topRowCount(html: string): number {
  return (html.match(/<li>/g) ?? []).length
}

describe('Dashboard im Browser-Markup', () => {
  it('zeigt Gesamtzahl, offene Findings und die Gesamtsumme deutsch formatiert', () => {
    const html = render()
    expect(html).toContain('Findings gesamt')
    expect(html).toContain('73.042,40 €')
    expect(html).toContain('davon <span class="font-mono tabular-nums">6</span> offen')
  })

  it('nennt die Euro-Wirkung je Kategorie', () => {
    const html = render()
    expect(html).toContain('Geldabfluss')
    expect(html).toContain('36.812,40 €')
    expect(html).toContain('27.300,00 €')
    expect(html).toContain('8.930,00 €')
    // Dubletten tragen keinen Betrag – und bekommen keinen erfundenen.
    expect(html).toContain('keine Euro-Wirkung')
    // Kein Betrag lautet auf null (als Teilzeichenkette steckt „0,00 €" in „27.300,00 €").
    expect(html).not.toMatch(/>0,00 €</)
  })

  it('zeigt alle vier Stufen als Anteil, auch die leere Stufe A', () => {
    const html = render()
    expect(html).toContain('0 von 6')
    expect(html).toContain('3 von 6')
    expect(html).toContain('2 von 6')
    expect(html).toContain('1 von 6')
  })

  it('listet die vier Findings mit Euro-Wirkung als klickbare Zeilen', () => {
    const html = render()
    expect(topRowCount(html)).toBe(4)
    expect(html).toContain('32.000,00 €')
    expect(html).toContain('2 Findings ohne Euro-Wirkung')
  })

  it('nennt in der Score-Kachel keine Zahl', () => {
    const html = render()
    const start = html.indexOf('Score')
    const score = html.slice(start, html.indexOf('</section>', start))
    expect(score).toContain('ab Sprint 4')
    // „4" steht nur im Wort „Sprint 4"; eine Kennzahl als eigener Textknoten gibt es nicht.
    expect(score).not.toMatch(/>\s*[0-9]+([.,][0-9]+)?\s*</)
  })

  it('erfindet bei einem leeren Lauf nichts', () => {
    const html = render([])
    expect(html).toContain('keine Findings')
    expect(html).not.toContain('€')
  })
})
