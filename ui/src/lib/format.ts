/**
 * Deutsche Formatierung für Beträge, Datum und Zeitstempel.
 *
 * Beträge kommen als String mit zwei Dezimalen aus dem Findings-JSON und werden
 * hier auch als String verarbeitet: kein `Number`, kein `parseFloat`, keine
 * Rundung (CLAUDE.md, Regel 2). Gerechnet wird über `bigint`-Cents.
 *
 * Alles ist deterministisch: keine Locale-Abhängigkeit, keine Zeitzone des
 * Browsers, kein `Date` (CLAUDE.md, Regel 9).
 */

/** Betrag als String mit zwei Dezimalen, optional negativ. */
const AMOUNT_PATTERN = /^(-?)([0-9]+)\.([0-9]{2})$/
const ISO_DATE_PATTERN = /^([0-9]{4})-([0-9]{2})-([0-9]{2})$/
const ISO_DATETIME_UTC_PATTERN =
  /^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]+)?Z$/

export class FormatError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'FormatError'
  }
}

/** Ganzzahlteil in Dreiergruppen mit Punkt: "32000" -> "32.000". */
function groupThousands(digits: string): string {
  let out = ''
  for (let i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 === 0) out += '.'
    out += digits[i]
  }
  return out
}

/**
 * "32000.00" -> "32.000,00". Ohne Währungszeichen.
 * Wirft `FormatError` bei allem, was nicht dem Betragsmuster entspricht –
 * lieber ein sichtbarer Fehler als ein stilles "NaN" (CLAUDE.md, Regel 4).
 */
export function formatDecimal(amount: string): string {
  const match = AMOUNT_PATTERN.exec(amount)
  if (!match) throw new FormatError(`Kein Betrag mit zwei Dezimalen: ${JSON.stringify(amount)}`)
  const [, rawSign, whole, fraction] = match
  // "-0.00" ist null – kein negatives Vorzeichen anzeigen.
  const isZero = /^0+$/.test(whole) && fraction === '00'
  const sign = rawSign === '-' && !isZero ? '-' : ''
  return `${sign}${groupThousands(whole)},${fraction}`
}

/** "32000.00" -> "32.000,00 €". */
export function formatEur(amount: string): string {
  return `${formatDecimal(amount)} €`
}

/**
 * Betrag als `bigint`-Cents. Grundlage für jede Summe – niemals über `number`
 * addieren, sonst wandern Beträge in die Fließkomma-Ungenauigkeit.
 */
export function parseCents(amount: string): bigint {
  const match = AMOUNT_PATTERN.exec(amount)
  if (!match) throw new FormatError(`Kein Betrag mit zwei Dezimalen: ${JSON.stringify(amount)}`)
  const [, sign, whole, fraction] = match
  const cents = BigInt(whole) * 100n + BigInt(fraction)
  return sign === '-' ? -cents : cents
}

/** Cents zurück in die kanonische Schreibweise: 3200000n -> "32000.00". */
export function centsToAmount(cents: bigint): string {
  const negative = cents < 0n
  const absolute = negative ? -cents : cents
  const whole = absolute / 100n
  const fraction = (absolute % 100n).toString().padStart(2, '0')
  return `${negative ? '-' : ''}${whole}.${fraction}`
}

/** Summiert Beträge exakt. Leere Liste -> "0.00". */
export function sumEur(amounts: readonly string[]): string {
  let total = 0n
  for (const amount of amounts) total += parseCents(amount)
  return centsToAmount(total)
}

/** "2026-08-28" -> "28.08.2026". */
export function formatDate(date: string): string {
  const match = ISO_DATE_PATTERN.exec(date)
  if (!match) throw new FormatError(`Kein ISO-Datum: ${JSON.stringify(date)}`)
  const [, year, month, day] = match
  return `${day}.${month}.${year}`
}

/**
 * "2026-08-30T09:15:00Z" -> "30.08.2026 09:15 UTC".
 *
 * Bewusst ohne Umrechnung in die Zeitzone des Browsers: derselbe Lauf muss überall
 * gleich aussehen, und der Zeitstempel gehört zum Lauf, nicht zum Betrachter.
 */
export function formatDateTime(timestamp: string): string {
  const match = ISO_DATETIME_UTC_PATTERN.exec(timestamp)
  if (!match) throw new FormatError(`Kein UTC-Zeitstempel: ${JSON.stringify(timestamp)}`)
  const [, year, month, day, hour, minute] = match
  return `${day}.${month}.${year} ${hour}:${minute} UTC`
}

/**
 * Wie `formatDate`, gibt aber `null` statt eines Fehlers zurück, wenn nichts da ist.
 * Für optionale Felder wie `relevance.last_activity_on`.
 */
export function formatDateOrNull(date: string | null | undefined): string | null {
  return date == null ? null : formatDate(date)
}

/** Wie `formatEur`, aber `null` bei fehlendem Betrag. */
export function formatEurOrNull(amount: string | null | undefined): string | null {
  return amount == null ? null : formatEur(amount)
}
