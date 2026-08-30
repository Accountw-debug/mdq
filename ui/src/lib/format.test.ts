import { describe, expect, it } from 'vitest'
import {
  FormatError,
  centsToAmount,
  formatDate,
  formatDateOrNull,
  formatDateTime,
  formatDecimal,
  formatEur,
  formatEurOrNull,
  parseCents,
  sumEur,
} from './format'

describe('formatEur', () => {
  it('formatiert den Beispielbetrag aus der Spec', () => {
    expect(formatEur('32000.00')).toBe('32.000,00 €')
  })

  it('formatiert alle Euro-Wirkungen der sechs Beispiel-Findings', () => {
    expect(formatEur('8930.00')).toBe('8.930,00 €')
    expect(formatEur('4812.40')).toBe('4.812,40 €')
    expect(formatEur('27300.00')).toBe('27.300,00 €')
    expect(formatEur('1284000.00')).toBe('1.284.000,00 €')
  })

  it('setzt Gruppentrenner erst ab vier Stellen', () => {
    expect(formatDecimal('0.00')).toBe('0,00')
    expect(formatDecimal('9.99')).toBe('9,99')
    expect(formatDecimal('99.50')).toBe('99,50')
    expect(formatDecimal('999.00')).toBe('999,00')
    expect(formatDecimal('1000.00')).toBe('1.000,00')
  })

  it('behandelt Vorzeichen', () => {
    expect(formatEur('-8930.00')).toBe('-8.930,00 €')
    expect(formatEur('-0.01')).toBe('-0,01 €')
  })

  it('zeigt "-0.00" ohne Minus', () => {
    expect(formatEur('-0.00')).toBe('0,00 €')
  })

  it('verarbeitet Beträge jenseits der Genauigkeit von Number', () => {
    // 2^53 Cent lägen jenseits von Number.MAX_SAFE_INTEGER – über bigint exakt.
    expect(formatDecimal('99999999999999999.99')).toBe('99.999.999.999.999.999,99')
  })

  it('wirft bei allem, was kein Betrag mit zwei Dezimalen ist', () => {
    for (const bad of ['32000', '32000.0', '32000.000', '32.000,00', '', ' 1.00', '1.00 ', 'abc', '1e3.00']) {
      expect(() => formatEur(bad)).toThrow(FormatError)
    }
  })

  it('gibt bei fehlendem Betrag null zurück', () => {
    expect(formatEurOrNull(null)).toBeNull()
    expect(formatEurOrNull(undefined)).toBeNull()
    expect(formatEurOrNull('4812.40')).toBe('4.812,40 €')
  })
})

describe('Cent-Arithmetik', () => {
  it('wandelt in Cents und zurück', () => {
    expect(parseCents('32000.00')).toBe(3200000n)
    expect(parseCents('4812.40')).toBe(481240n)
    expect(parseCents('-8930.00')).toBe(-893000n)
    expect(centsToAmount(481240n)).toBe('4812.40')
    expect(centsToAmount(-893000n)).toBe('-8930.00')
    expect(centsToAmount(5n)).toBe('0.05')
    expect(centsToAmount(0n)).toBe('0.00')
  })

  it('summiert die Euro-Wirkung der Beispiele auf 73.042,40 €', () => {
    // Erwartungswert aus docs/specs/SPRINT-5-UI.md, Aufgabe 6.
    const total = sumEur(['32000.00', '8930.00', '4812.40', '27300.00'])
    expect(total).toBe('73042.40')
    expect(formatEur(total)).toBe('73.042,40 €')
  })

  it('summiert die leere Liste zu null', () => {
    expect(sumEur([])).toBe('0.00')
  })

  it('summiert ohne Fließkomma-Drift', () => {
    // 0.1 + 0.2 !== 0.3 als float; über Cents stimmt es.
    expect(sumEur(['0.10', '0.20'])).toBe('0.30')
    expect(sumEur(Array.from({ length: 10 }, () => '0.07'))).toBe('0.70')
  })
})

describe('formatDate', () => {
  it('formatiert den Datenstand der Beispiele', () => {
    expect(formatDate('2026-08-28')).toBe('28.08.2026')
    expect(formatDate('2025-11-03')).toBe('03.11.2025')
  })

  it('rechnet nicht in die Zeitzone des Browsers um', () => {
    expect(formatDate('2026-01-01')).toBe('01.01.2026')
    expect(formatDate('2026-12-31')).toBe('31.12.2026')
  })

  it('wirft bei ungültigem Datum', () => {
    for (const bad of ['28.08.2026', '2026-8-28', '2026-08-28T00:00:00Z', '']) {
      expect(() => formatDate(bad)).toThrow(FormatError)
    }
  })

  it('gibt bei fehlendem Datum null zurück', () => {
    expect(formatDateOrNull(null)).toBeNull()
    expect(formatDateOrNull(undefined)).toBeNull()
    expect(formatDateOrNull('2026-08-12')).toBe('12.08.2026')
  })
})

describe('formatDateTime', () => {
  it('formatiert den Zeitstempel der Beispiele als UTC', () => {
    expect(formatDateTime('2026-08-30T09:15:00Z')).toBe('30.08.2026 09:15 UTC')
  })

  it('akzeptiert Sekundenbruchteile', () => {
    expect(formatDateTime('2026-08-30T09:15:00.123Z')).toBe('30.08.2026 09:15 UTC')
  })

  it('wirft bei Zeitstempeln ohne UTC-Kennzeichnung', () => {
    for (const bad of ['2026-08-30T09:15:00', '2026-08-30T09:15:00+02:00', '2026-08-30', '']) {
      expect(() => formatDateTime(bad)).toThrow(FormatError)
    }
  })
})
