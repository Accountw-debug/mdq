import { CrownIcon } from 'lucide-react'
import { Key } from '@/components/Key'
import { Section } from '@/components/review/Section'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { DuplicateComparison } from '@/lib/duplicate'
import { cn } from '@/lib/utils'
import type { Finding } from '@/types/finding'

/**
 * Dubletten-Vergleich (Spec Sprint 5, Aufgabe 4) – tritt bei `category: duplicate`
 * an die Stelle von Ist|Soll.
 *
 * Eine Spalte je Konto des Clusters, eine Zeile je Feld. Gleiche Werte treten zurück,
 * abweichende stehen vorn – die Frage am Schreibtisch lautet nicht „was steht da",
 * sondern „wo unterscheiden sie sich". Das führende Konto trägt die Krone.
 *
 * Die Vergleichswerte stammen aus `current.display`; welche Felder der Spec das
 * Finding nicht hergibt, steht unter der Tabelle. Zusammengebaut wird all das in
 * `@/lib/duplicate` – hier wird nur gezeichnet.
 */
export function DuplicateCompare({
  finding,
  comparison,
}: {
  finding: Finding
  comparison: DuplicateComparison
}) {
  const { accounts, rows, chips, matchNote, missingFields } = comparison
  const proposedDisplay = finding.proposed?.display?.trim()
  const sourceSummary = finding.proposed?.source_summary?.trim()

  return (
    <Section title="Dubletten-Vergleich">
      {chips.length > 0 && (
        <div className="mb-3">
          <div className="text-xs text-muted-foreground">Match-Gründe</div>
          <ul className="mt-1.5 flex flex-wrap gap-1.5">
            {chips.map((chip) => (
              <li
                key={chip}
                className="rounded-full border bg-muted/40 px-2.5 py-0.5 text-xs whitespace-nowrap"
              >
                {chip}
              </li>
            ))}
          </ul>
          {matchNote && <p className="mt-1.5 text-xs text-muted-foreground">{matchNote}</p>}
        </div>
      )}

      {/* `Table` bringt seinen eigenen waagerechten Scroller mit – bei mehr als zwei
          Konten wandert die Tabelle, die Karte bleibt stehen. */}
      <Table className="text-sm">
        <TableHeader>
          <TableRow>
            <TableHead className="w-36 align-bottom text-xs font-medium">Feld</TableHead>
            {accounts.map((account) => (
              <TableHead key={account.bpKey} className="align-bottom">
                <span className="flex items-center gap-1.5">
                  {account.isLead && (
                    <>
                      <CrownIcon className="size-3.5 shrink-0" aria-hidden />
                      <span className="sr-only">Führendes Konto: </span>
                    </>
                  )}
                  <Key className="text-foreground">{account.bpKey}</Key>
                </span>
                {account.isLead && (
                  <span className="mt-0.5 block text-xs font-normal text-muted-foreground">
                    Führendes Konto
                  </span>
                )}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        {rows.length > 0 && (
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.label}>
                <TableCell className="align-top text-xs text-muted-foreground">
                  {row.label}
                </TableCell>
                {row.cells.map((cell, index) => (
                  <TableCell
                    key={accounts[index].bpKey}
                    className={cn(
                      'align-top break-words whitespace-normal',
                      row.differs ? 'bg-muted/50 font-medium' : 'text-muted-foreground',
                    )}
                  >
                    {cell ?? <span className="italic">leer</span>}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        )}
      </Table>

      {/*
        Was das Finding nicht hergibt, wird benannt statt als leere Zeile gezeigt
        (Freigabe Victor). Sechs Zeilen mit „–" sähen nach einer Lücke im Mandanten
        aus; es ist eine Lücke im Schema.
      */}
      {missingFields.length > 0 && (
        <p className="mt-2 text-xs text-muted-foreground">
          <span className="font-medium">Platzhalter:</span> Für den Vergleich fehlen{' '}
          {missingFields.join(', ')}. Diese Felder stehen nicht strukturiert im Finding;
          sie kommen mit der vorgeschlagenen Schema-Erweiterung <Key>entity.records</Key>.
        </p>
      )}

      {(proposedDisplay || sourceSummary) && (
        <div className="mt-3 rounded-lg border p-3">
          <div className="text-xs font-medium">Soll</div>
          {proposedDisplay && <p className="mt-1 break-words">{proposedDisplay}</p>}
          {sourceSummary && (
            <p className={cn('text-xs', proposedDisplay ? 'mt-2 border-t pt-2' : 'mt-1')}>
              <span className="text-muted-foreground">Quellenlage: </span>
              {sourceSummary}
            </p>
          )}
        </div>
      )}
    </Section>
  )
}
