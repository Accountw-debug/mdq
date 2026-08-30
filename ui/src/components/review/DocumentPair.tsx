import { CheckIcon, XIcon } from 'lucide-react'
import { Key } from '@/components/Key'
import { LabelValue, Section } from '@/components/review/Section'
import type { DocumentCard as DocumentCardData, DocumentPair } from '@/lib/documents'
import { formatDateOrNull } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Evidence } from '@/types/finding'

/**
 * Belegpaar-Ansicht (Spec Sprint 5, Aufgabe 5) – zwei Belegkarten nebeneinander,
 * darunter der Fuzzy-Grund und der Netting-Nachweis.
 *
 * Sie steht **vor** Ist|Soll (Freigabe Victor): bei einer Doppelzahlung lautet die
 * erste Frage „welche zwei Belege", erst danach „welches Feld". Ist|Soll bleibt
 * daneben bestehen – anders als bei der Dublette steht dort mit `BSAK.XBLNR` das
 * konkrete Feld, und der fehlende Bindestrich in der Referenz ist der Kern.
 *
 * Zusammengebaut wird alles in `@/lib/documents` – hier wird nur gezeichnet.
 */
export function DocumentPairSection({ pair }: { pair: DocumentPair }) {
  const { cards, fuzzyReason, netting, missingFields } = pair

  return (
    <Section title={cards.length === 2 ? 'Belegpaar' : `Belege (${cards.length})`}>
      {/* Zwei Karten erst, wenn jede einen ganzen Satz tragen kann (~19rem je Spalte). */}
      <div className="grid gap-3 @min-[38rem]:grid-cols-2">
        {cards.map((card) => (
          <DocumentCard key={card.key} card={card} />
        ))}
      </div>

      {/*
        Was das Finding je Beleg nicht hergibt, wird benannt statt geraten: der Betrag
        steht nur als Euro-Wirkung des Findings da, nicht je Beleg.
      */}
      {missingFields.length > 0 && (
        <p className="mt-2 text-xs text-muted-foreground">
          <span className="font-medium">Platzhalter:</span> {missingFields.join(', ')} je Beleg
          steht nicht strukturiert im Finding – kommt mit <Key>entity.documents</Key>.
        </p>
      )}

      {fuzzyReason && (
        <div className="mt-3 rounded-lg border p-3">
          <div className="text-xs font-medium">Warum dieses Paar</div>
          <p className="mt-1 text-sm break-words">{fuzzyReason}</p>
        </div>
      )}

      {netting && <NettingProof entry={netting} />}
    </Section>
  )
}

function DocumentCard({ card }: { card: DocumentCardData }) {
  const { document, facts, raw, evidence } = card
  const observedAt = formatDateOrNull(evidence.observed_at)

  return (
    <div className="rounded-lg border bg-muted/30 p-3">
      <div className="flex items-baseline justify-between gap-2">
        <Key className="text-[0.95em] break-all">{card.key}</Key>
        {document.line_item && (
          <span className="shrink-0 text-xs text-muted-foreground">
            Position <Key>{document.line_item}</Key>
          </span>
        )}
      </div>

      {facts ? (
        <dl className="mt-2 grid gap-2">
          <LabelValue label="Referenz">
            <Key className="text-[0.95em] break-all">{facts.reference}</Key>
          </LabelValue>
          <LabelValue label="Belegdatum">
            <Key className="text-[0.95em]">{facts.documentDate}</Key>
          </LabelValue>
          <LabelValue label="Bezahlt am">
            <Key className="text-[0.95em]">{facts.clearedOn}</Key>
          </LabelValue>
        </dl>
      ) : (
        raw && <p className="mt-2 text-sm break-words">{raw}</p>
      )}

      {evidence.note && (
        <p className="mt-2 border-t pt-2 text-xs text-muted-foreground">{evidence.note}</p>
      )}
      {observedAt && !facts && (
        <p className="mt-1 text-xs text-muted-foreground">Beobachtet {observedAt}</p>
      )}
    </div>
  )
}

/**
 * Der Netting-Nachweis: wurde die zweite Zahlung schon gutgeschrieben oder storniert?
 * Ohne diese Antwort ist die Euro-Wirkung nicht belastbar, deshalb steht sie hier und
 * nicht nur als eine Karte unter anderen im Evidenz-Panel.
 */
function NettingProof({ entry }: { entry: Evidence }) {
  const Icon = entry.agrees ? CheckIcon : XIcon
  const observedAt = formatDateOrNull(entry.observed_at)

  return (
    <div className="mt-2 rounded-lg border p-3">
      <div className="flex items-baseline gap-2">
        <span
          className={cn(
            'inline-flex items-center',
            entry.agrees ? 'text-emerald-600 dark:text-emerald-400' : 'text-destructive',
          )}
        >
          <Icon className="size-4" aria-hidden />
        </span>
        <div className="min-w-0 flex-1 text-xs font-medium">Netting-Nachweis</div>
        {observedAt && <span className="shrink-0 text-xs text-muted-foreground">{observedAt}</span>}
      </div>
      {entry.value && (
        <p className="mt-1 break-words">
          <Key className="text-[0.95em]">{entry.value}</Key>
        </p>
      )}
      <p className="mt-1 text-xs text-muted-foreground">
        Gesucht in <Key>{entry.reference}</Key>
      </p>
    </div>
  )
}
