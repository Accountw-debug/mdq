/**
 * Regelgruppen und Stichproben-Freigabe (Spec Sprint 5, Aufgabe 7) – reine
 * Funktionen ohne React.
 *
 * Der Gedanke: eine Massenänderung wird nicht Finding für Finding entschieden,
 * sondern die Regel wird an einer Stichprobe geprüft und dann als Ganzes
 * freigegeben. Damit die Prüfung nachvollziehbar bleibt, hängt die Auswahl an
 * einem festen Seed aus Lauf und Regel – gleicher Lauf, gleiche offene Menge,
 * gleiche Stichprobe (CLAUDE.md, Regel 9). Kein `Math.random`.
 *
 * Zwei Riegel liegen hier und nicht in der Oberfläche:
 * - Schadensklasse 1 wird nie über eine Gruppe entschieden (Regel 11).
 * - Eine Ablehnung in der Stichprobe sperrt die Freigabe der Gruppe für diesen
 *   Lauf endgültig (Freigabe Victor, 2026-08-30); die übrigen Findings der Gruppe
 *   bleiben einzeln entscheidbar.
 */

import { sumByCurrency, type MoneyTotal } from '@/lib/dashboard'
import { createDecision, isOpen } from '@/lib/review'
import { impactCents } from '@/lib/select-findings'
import type { DecisionsState } from '@/state/decisions'
import type { DecisionRecord } from '@/types/decision'
import type { SampleReview } from '@/types/decisions-file'
import type { Finding, Tier } from '@/types/finding'

/** Höchstzahl der geprüften Findings je Gruppe (Spec Sprint 5, Aufgabe 7). */
export const SAMPLE_SIZE = 10

export interface RuleGroup {
  rule_id: string
  rule_version: string
  /** Titel des ersten Findings – innerhalb einer Regel ist er derselbe Satz. */
  title: string
  /** Stufe der Gruppe; bei gemischten Stufen die des ersten Findings. */
  tier: Tier
  mixedTier: boolean
  /** Alle Findings der Gruppe, in der Reihenfolge, in der sie hereinkamen. */
  findings: Finding[]
  total: number
  open: number
  /** Offen und nicht Schadensklasse 1 – nur diese kann eine Gruppenfreigabe treffen. */
  releasable: number
  /** Schadensklasse 1 in der Gruppe. Wird genannt, nie mitfreigegeben (Regel 11). */
  bankData: number
  totals: MoneyTotal[]
}

/** Darf dieses Finding über eine Gruppenfreigabe entschieden werden? */
export function isReleasable(finding: Finding): boolean {
  return finding.damage_class !== 1
}

function compareText(a: string, b: string): number {
  if (a < b) return -1
  if (a > b) return 1
  return 0
}

function compareCents(a: bigint, b: bigint): number {
  if (a < b) return -1
  if (a > b) return 1
  return 0
}

function totalCents(findings: readonly Finding[]): bigint {
  return findings.reduce((sum, finding) => sum + impactCents(finding), 0n)
}

/**
 * Findings des Tabs Massenänderung nach Regel gruppiert.
 *
 * Grundlage ist der ganze Tab, nicht die gefilterte Tabelle: die Gruppen
 * beschreiben, was die Regel im Lauf gefunden hat – ein eingestellter Filter ist
 * eine Sicht darauf, kein anderer Befund. Reihenfolge: Euro-Wirkung absteigend,
 * dann Regel-ID (Regel 9).
 */
export function groupByRule(findings: readonly Finding[]): RuleGroup[] {
  const buckets = new Map<string, Finding[]>()
  for (const finding of findings) {
    const bucket = buckets.get(finding.rule_id)
    if (bucket == null) buckets.set(finding.rule_id, [finding])
    else bucket.push(finding)
  }

  return [...buckets.entries()]
    .map(([ruleId, group]) => {
      const first = group[0]
      const open = group.filter(isOpen)
      return {
        rule_id: ruleId,
        rule_version: first.rule_version,
        title: first.title,
        tier: first.tier,
        mixedTier: group.some((finding) => finding.tier !== first.tier),
        findings: group,
        total: group.length,
        open: open.length,
        releasable: open.filter(isReleasable).length,
        bankData: group.filter((finding) => !isReleasable(finding)).length,
        totals: sumByCurrency(group),
      }
    })
    .sort((a, b) => {
      const byImpact = compareCents(totalCents(b.findings), totalCents(a.findings))
      return byImpact !== 0 ? byImpact : compareText(a.rule_id, b.rule_id)
    })
}

/** Findings, aus denen eine Stichprobe gezogen wird: offen und ohne Bankdaten. */
export function sampleCandidates(group: RuleGroup): Finding[] {
  return group.findings.filter((finding) => isOpen(finding) && isReleasable(finding))
}

/**
 * Seed aus Lauf und Regel (FNV-1a, 32 Bit). Zwei Läufe ziehen verschiedene
 * Stichproben, derselbe Lauf immer dieselbe – ohne dass irgendwo ein Zustand
 * gespeichert werden müsste.
 */
export function sampleSeed(runId: string, ruleId: string): number {
  let hash = 0x811c9dc5
  for (const char of `${runId}|${ruleId}`) {
    hash ^= char.codePointAt(0) ?? 0
    hash = Math.imul(hash, 0x01000193)
  }
  return hash >>> 0
}

/** mulberry32: kleiner, deterministischer Zufall – Werte in [0, 1). */
function randomFrom(seed: number): () => number {
  let state = seed >>> 0
  return () => {
    state = (state + 0x6d2b79f5) >>> 0
    let t = state
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/**
 * Zieht bis zu `size` Findings aus den Kandidaten.
 *
 * Gemischt wird über die nach `finding_id` sortierte Liste, damit die Auswahl
 * nicht davon abhängt, in welcher Reihenfolge die Tabelle gerade sortiert ist.
 * Zurück kommt sie in der Reihenfolge der übergebenen Liste – geprüft wird von
 * oben nach unten wie in der Tabelle.
 */
export function drawSample(
  candidateIds: readonly string[],
  seed: number,
  size: number = SAMPLE_SIZE,
): string[] {
  const pool = [...candidateIds].sort(compareText)
  const take = Math.min(size, pool.length)
  const random = randomFrom(seed)
  for (let i = 0; i < take; i++) {
    const j = i + Math.floor(random() * (pool.length - i))
    ;[pool[i], pool[j]] = [pool[j], pool[i]]
  }
  const chosen = new Set(pool.slice(0, take))
  return candidateIds.filter((id) => chosen.has(id))
}

/** Stichprobe einer Gruppe – die eine Stelle, an der Seed und Kandidaten zusammenkommen. */
export function sampleForGroup(group: RuleGroup, size: number = SAMPLE_SIZE): string[] {
  const candidates = sampleCandidates(group)
  if (candidates.length === 0) return []
  const seed = sampleSeed(candidates[0].run_id, group.rule_id)
  return drawSample(
    candidates.map((finding) => finding.finding_id),
    seed,
    size,
  )
}

export interface SampleProgress {
  size: number
  decided: number
  accepted: number
  assigned: number
  /** Das erste abgelehnte Finding der Stichprobe – es sperrt die Gruppe. */
  rejectedId: string | null
}

/** Stand der Stichprobe: was ist entschieden, was übernommen, was abgelehnt? */
export function sampleProgress(
  sampledIds: readonly string[],
  decisions: DecisionsState,
): SampleProgress {
  let decided = 0
  let accepted = 0
  let assigned = 0
  let rejectedId: string | null = null
  for (const id of sampledIds) {
    const record = decisions[id]
    if (record == null) continue
    decided += 1
    if (record.action === 'accept') accepted += 1
    if (record.action === 'assign') assigned += 1
    if (record.action === 'reject' && rejectedId == null) rejectedId = id
  }
  return { size: sampledIds.length, decided, accepted, assigned, rejectedId }
}

/**
 * Was nach einer Entscheidung in der Stichprobe geschieht:
 *
 * - `blocked`: abgelehnt – die Gruppenfreigabe ist für diesen Lauf erledigt.
 * - `continue`: es sind noch gezogene Findings offen.
 * - `release`: alle geprüft und übernommen – die Rückfrage darf kommen.
 * - `incomplete`: alle geprüft, aber nicht alle übernommen (etwa zugewiesen).
 *   Keine Freigabe, aber auch keine Sperre: erst klären, dann erneut ziehen.
 */
export type SampleStep = 'blocked' | 'continue' | 'release' | 'incomplete'

export function nextSampleStep(progress: SampleProgress): SampleStep {
  if (progress.rejectedId != null) return 'blocked'
  if (progress.decided < progress.size) return 'continue'
  return progress.accepted === progress.size ? 'release' : 'incomplete'
}

/** Grund des freigegebenen Findings – er steht später in `decisions.json`. */
export function releaseReason(sampleSize: number, groupSize: number): string {
  return `Über Stichprobe der Regelgruppe freigegeben (${sampleSize} von ${groupSize} geprüft)`
}

/**
 * Die Gruppenfreigabe: je noch offenem, freigebbarem Finding eine Entscheidung
 * `accept` – Status also `in_progress`, nicht `done`. Entschieden ist nicht
 * umgesetzt; `done` vergibt erst der nächste Lauf, in dem das Finding fehlt
 * (Freigabe Victor, 2026-08-30, gegen die ältere Spec-Stelle).
 *
 * Schon entschiedene Findings bleiben unangetastet – auch die der Stichprobe,
 * die ihren eigenen Grund behalten.
 */
export function buildGroupRelease(
  group: RuleGroup,
  sampledIds: readonly string[],
  decisions: DecisionsState,
  by: string,
  now: () => string = () => new Date().toISOString(),
): { review: SampleReview; records: DecisionRecord[] } {
  const at = now()
  const clock = () => at
  const reason = releaseReason(sampledIds.length, group.total)
  const records = group.findings
    .filter(
      (finding) =>
        isReleasable(finding) && isOpen(finding) && decisions[finding.finding_id] == null,
    )
    .map((finding) =>
      createDecision(
        { findingId: finding.finding_id, action: 'accept', by, reason },
        clock,
      ),
    )

  return {
    review: {
      rule_id: group.rule_id,
      outcome: 'released',
      sampled_finding_ids: [...sampledIds],
      applied_finding_ids: records.map((record) => record.finding_id).sort(compareText),
      blocked_by_finding_id: null,
      by: by.trim(),
      at,
    },
    records,
  }
}

/**
 * Die gesperrte Gruppe: ein Finding der Stichprobe wurde abgelehnt, also stimmt
 * die Regel hier nicht pauschal. Der Satz hält fest, woran es lag – die übrigen
 * Findings bleiben offen und einzeln entscheidbar.
 */
export function buildGroupBlock(
  group: RuleGroup,
  sampledIds: readonly string[],
  blockedBy: string,
  by: string,
  now: () => string = () => new Date().toISOString(),
): SampleReview {
  return {
    rule_id: group.rule_id,
    outcome: 'blocked',
    sampled_finding_ids: [...sampledIds],
    applied_finding_ids: [],
    blocked_by_finding_id: blockedBy,
    by: by.trim(),
    at: now(),
  }
}
