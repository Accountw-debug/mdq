/**
 * Rauchtest der Review-Karte mit allen sechs Beispiel-Findings.
 *
 * `ReviewCard` hängt bewusst in keinem Portal (anders als der Drawer), deshalb
 * lässt sie sich mit `renderToStaticMarkup` in der Node-Umgebung prüfen – ohne
 * jsdom und ohne Testing Library. Was hier steht, ist die Abnahme aus der Spec:
 * alle sechs vollständig, keine leeren Abschnitte, Schadensklasse 1 gesperrt.
 */
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { load as loadYaml } from 'js-yaml'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ReviewCard } from '@/components/review/ReviewCard'
import { TooltipProvider } from '@/components/ui/tooltip'
import type { DecisionRecord } from '@/types/decision'
import type { Finding } from '@/types/finding'

const EXAMPLES_DIR = fileURLToPath(new URL('../../../../logic/examples/findings', import.meta.url))

const examples: Finding[] = readdirSync(EXAMPLES_DIR)
  .filter((name) => name.endsWith('.yaml'))
  .sort()
  .map((name) => loadYaml(readFileSync(join(EXAMPLES_DIR, name), 'utf8')) as Finding)

function byId(findingId: string): Finding {
  const found = examples.find((example) => example.finding_id === findingId)
  if (!found) throw new Error(`Beispiel fehlt: ${findingId}`)
  return found
}

function render(
  finding: Finding,
  options: { reviewer?: string; decision?: DecisionRecord } = {},
): string {
  return renderToStaticMarkup(
    <TooltipProvider>
      <ReviewCard
        finding={finding}
        decision={options.decision}
        reviewer={options.reviewer ?? 'V. Test'}
        onDecide={() => {}}
        onClearDecision={() => {}}
        onLater={() => {}}
        onMove={() => {}}
      />
    </TooltipProvider>,
  )
}

/**
 * Ist der Knopf mit dieser Beschriftung gesperrt? Geprüft wird das Attribut
 * `disabled=""` – die Klassenliste enthält mit `disabled:opacity-50` schon das Wort.
 *
 * Gesucht wird nur innerhalb der Knöpfe: „Übernehmen" steht auch in der Zeile der
 * getroffenen Entscheidung, und die kommt im Markup vor den Knöpfen.
 */
function disabled(html: string, label: string): boolean {
  const fragment = html
    .split('<button')
    .slice(1)
    .map((part) => part.slice(0, part.indexOf('</button>')))
    .find((part) => part.includes(label))
  if (fragment == null) throw new Error(`Knopf fehlt: ${label}`)
  return fragment.includes('disabled=""')
}

describe('Review-Karte für alle sechs Beispiele', () => {
  it.each(examples.map((example) => [example.finding_id, example] as const))(
    '%s zeigt Kopf, Erklärung und Behebung',
    (_id, finding) => {
      const html = render(finding)
      expect(html).toContain(finding.entity.bp_key)
      expect(html).toContain(finding.rule_id)
      if (finding.title) expect(html).toContain(finding.title)
      // Bei Dubletten tritt der Vergleich an die Stelle von Ist|Soll (Aufgabe 4).
      expect(html).toContain(
        finding.category === 'duplicate' ? 'Dubletten-Vergleich' : 'Ist und Soll',
      )
      expect(html).toContain('Warum')
      expect(html).toContain('Wenn falsch')
      expect(html).toContain('Wie beheben')
      expect(html).toContain(finding.remediation.sap_transaction)
      expect(html).toContain('Relevanz')
    },
  )

  it.each(examples.map((example) => [example.finding_id, example] as const))(
    '%s lässt keinen Abschnitt leer stehen',
    (_id, finding) => {
      const html = render(finding)
      // Eine Überschrift ohne Inhalt wäre genau das, was die Spec ausschließt.
      expect(html).not.toMatch(/<h3[^>]*>[^<]+<\/h3><div[^>]*><\/div>/)
    },
  )

  it('blendet die Euro-Wirkung aus, wenn das Finding keine hat', () => {
    expect(render(byId('F-3a9f1c2d4e5b'))).not.toContain('Euro-Wirkung')
    expect(render(byId('F-7b2e8c1d9a3f'))).not.toContain('Euro-Wirkung')
  })

  it('zeigt Betrag, Rechenweg und Evidenz der Doppelzahlung', () => {
    const html = render(byId('F-c41d7e9b2a60'))
    expect(html).toContain('32.000,00 €')
    expect(html).toContain('Betrag der zweiten Zahlung 32.000,00 EUR')
    expect(html).toContain('1900004411')
    expect(html).toContain('1900004587')
    expect(html).toContain('Evidenz (3)')
    expect(html).toContain('Rechnung B')
  })

  it('zeigt bei der Entscheidung beide Optionen mit ihrer Konsequenz', () => {
    const html = render(byId('F-9d0b3f6a1c7e'))
    expect(html).toContain('Löschvormerkung aufheben, Posten normal mahnen')
    expect(html).toContain('Konto nimmt wieder am Mahnlauf teil')
    expect(html).toContain('Posten ausbuchen oder umbuchen')
    expect(html).toContain('Optionen')
    // Ohne gewählte Option ist „Übernehmen" gesperrt.
    expect(disabled(html, 'Übernehmen')).toBe(true)
  })

  it('sperrt bei Schadensklasse 1 das Übernehmen und stellt den Widerspruch nach vorn', () => {
    const html = render(byId('F-e2f7b19c4d83'))
    expect(disabled(html, 'Übernehmen')).toBe(true)
    expect(disabled(html, 'Ablehnen')).toBe(false)
    expect(html).toContain('widerspricht dem Soll')
    expect(html.indexOf('Mod-97-Prüfung')).toBeLessThan(html.indexOf('Wie beheben'))
    expect(html).toContain('Deshalb Schadensklasse 1')
  })

  it('nennt Ist mit Tabelle und Feld', () => {
    const html = render(byId('F-3a9f1c2d4e5b'))
    expect(html).toContain('KNA1.STCEG')
    expect(html).toContain('DE123456780')
    expect(html).toContain('Quellenlage')
  })

  it('sperrt jede Entscheidung, solange kein Bearbeiter eingetragen ist', () => {
    const html = render(byId('F-c41d7e9b2a60'), { reviewer: '   ' })
    for (const label of ['Übernehmen', 'Ablehnen', 'Zuweisen']) {
      expect(disabled(html, label)).toBe(true)
    }
    expect(disabled(html, 'Später')).toBe(false)
    expect(html).toContain('Bearbeiter eintragen')
  })

  it('zeigt eine getroffene Entscheidung mit Grund und Zeitpunkt', () => {
    const html = render(byId('F-c41d7e9b2a60'), {
      decision: {
        finding_id: 'F-c41d7e9b2a60',
        action: 'accept',
        reason_code: null,
        reason: 'Vorschlag übernommen',
        assigned_to: null,
        by: 'V. Test',
        at: '2026-08-30T10:00:00.000Z',
      },
    })
    expect(html).toContain('freigegeben – Umsetzung offen')
    expect(html).toContain('30.08.2026 10:00 UTC')
    expect(html).toContain('Zurücknehmen')
  })

  it('nennt die Spalte „Empfehlung", wenn nur proposed.display vorliegt', () => {
    // F-e2f7b19c4d83 hat kein `proposed.value`, aber einen Handlungssatz. Der feste
    // Hinweis wäre hier falsch – es gibt sehr wohl ein Soll, nur keinen Feldwert.
    const html = render(byId('F-e2f7b19c4d83'))
    expect(html).toContain('Empfehlung')
    expect(html).not.toContain('Kein Soll ermittelbar – Entscheidung/Prüfung')
    expect(html).toContain('Anfrage an Lieferant')
  })

  it('nennt den Hinweis nur, wenn weder Wert noch Text vorliegen', () => {
    // F-9d0b3f6a1c7e: `value` und `display` sind null, es gibt nur Optionen.
    const html = render(byId('F-9d0b3f6a1c7e'))
    expect(html).toContain('Kein Soll ermittelbar – Entscheidung/Prüfung')
    expect(html).not.toContain('Empfehlung')
  })

  it('führt in der Evidenz die Referenz vor dem Quellentyp', () => {
    const html = render(byId('F-c41d7e9b2a60'))
    const reference = html.indexOf('1000/2026/1900004411')
    const sourceType = html.indexOf('Regelprüfung')
    expect(reference).toBeGreaterThan(-1)
    expect(sourceType).toBeGreaterThan(reference)
  })

  it('zeigt bei der Dublette beide Konten statt Ist und Soll', () => {
    const html = render(byId('F-7b2e8c1d9a3f'))
    expect(html).toContain('Dubletten-Vergleich')
    expect(html).not.toContain('Ist und Soll')
    expect(html).toContain('C:0000100234')
    expect(html).toContain('C:0000100987')
  })

  it('zerlegt die Adresszeile und hebt nur die abweichenden Zeilen hervor', () => {
    const html = render(byId('F-7b2e8c1d9a3f'))
    for (const label of ['Name', 'Straße', 'PLZ/Ort']) expect(html).toContain(label)
    expect(html).toContain('Müller Maschinenbau GmbH')
    expect(html).toContain('Mueller Maschinenbau GmbH')
    // Die gleiche PLZ/Ort-Zeile tritt zurück, die abweichenden stehen vorn.
    expect(html).toMatch(/bg-muted\/50[^>]*>Müller Maschinenbau GmbH/)
    expect(html).toMatch(/text-muted-foreground[^>]*>86159 Augsburg/)
  })

  it('nennt die drei Match-Gründe als Chips und markiert das führende Konto', () => {
    const html = render(byId('F-7b2e8c1d9a3f'))
    for (const chip of ['name_norm gleich', 'street_norm gleich', 'postal_code gleich']) {
      expect(html).toContain(chip)
    }
    // Die Notiz der Modell-Evidenz steht als Satz unter den Chips.
    expect(html).toContain('Transliteration')
    expect(html).toContain('Führendes Konto')
    // Die Krone hängt am ersten Konto, nicht am zweiten.
    expect(html.indexOf('Führendes Konto')).toBeLessThan(html.indexOf('C:0000100987'))
  })

  it('benennt die Felder, die das Finding für den Vergleich nicht hergibt', () => {
    const html = render(byId('F-7b2e8c1d9a3f'))
    expect(html).toContain('Platzhalter:')
    expect(html).toContain('entity.records')
    for (const field of ['Land', 'USt-ID', 'IBAN', 'Zahlungsbedingung']) {
      expect(html).toContain(field)
    }
  })

  it('behält bei der Dublette Soll und Quellenlage unter der Tabelle', () => {
    const html = render(byId('F-7b2e8c1d9a3f'))
    expect(html).toContain('Führendes Konto 0000100234')
    expect(html).toContain('Quellenlage: ')
    expect(html.indexOf('Dubletten-Vergleich')).toBeLessThan(html.indexOf('Quellenlage: '))
  })

  it('sperrt nach einer Entscheidung alles außer Zurücknehmen und Später', () => {
    const html = render(byId('F-c41d7e9b2a60'), {
      decision: {
        finding_id: 'F-c41d7e9b2a60',
        action: 'accept',
        reason_code: null,
        reason: 'Vorschlag übernommen',
        assigned_to: null,
        by: 'V. Test',
        at: '2026-08-30T10:00:00.000Z',
      },
    })
    for (const label of ['Übernehmen', 'Ablehnen', 'Zuweisen']) {
      expect(disabled(html, label)).toBe(true)
    }
    expect(disabled(html, 'Zurücknehmen')).toBe(false)
    expect(disabled(html, 'Später')).toBe(false)
  })
})
