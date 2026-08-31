/**
 * Der Vertrag, über den das UI an Findings kommt.
 *
 * Alle Ansichten lesen ausschließlich `LoadedRun`; woher die Daten stammen –
 * `public/data/` des Build-Skripts, eine gewählte Datei, später ein Lauf-Verzeichnis
 * oder eine API – weiß nur die Implementierung. Ein Backend tauscht `DEFAULT_SOURCE`
 * in `@/sources`, sonst nichts (ui/NOTES.md, 2026-08-30: UI ist Produktcode).
 *
 * Zum Vertrag gehört mehr als die Signatur:
 * - Jede Implementierung schleust ihre Daten durch `@/sources/parse` – dieselben
 *   Pflichtfeld-Prüfungen für Datei und API.
 * - Fehler verlassen eine Quelle **immer** als `LoadError` mit deutscher Meldung,
 *   nie als roher `fetch`- oder `JSON.parse`-Fehler (CLAUDE.md, Regel 4).
 * - Meldungen nennen nur Feldnamen, Regel-IDs und `finding_id`, nie
 *   Geschäftspartnerdaten (Regel 8).
 */

import type { Finding, RunInfo } from '@/types/finding'

/** Woher die gezeigten Findings stammen – für den Hinweis im Datenstand-Banner. */
export type SourceKind = 'build' | 'file'

export interface LoadedRun {
  run: RunInfo
  findings: Finding[]
}

export interface FindingsSource {
  readonly kind: SourceKind
  /** Kurzbezeichnung im Banner: „Beispiel-Findings", ein Dateiname, später eine Lauf-ID. */
  readonly label: string
  /** Lädt genau einen Lauf. Bricht mit `LoadError` ab, nie mit einem rohen Fehler. */
  loadRun(signal?: AbortSignal): Promise<LoadedRun>
}

export class LoadError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'LoadError'
  }
}
