/**
 * Wandelt die Beispiel-Findings aus `logic/examples/findings/*.yaml` in die beiden
 * JSON-Dateien um, die die Anwendung ohne gewählte Datei lädt:
 *
 *   ui/public/data/findings.json  – Array von Findings
 *   ui/public/data/run.json       – Ersatz-Lauf-Kopf, aus den Findings abgeleitet
 *
 * **Dieses Skript ist der Ersatz für die sechs Beispiel-Findings, kein Lauf.**
 * Seit Sprint 3 schreibt `mdq run` ein Lauf-Verzeichnis `runs/<run_id>/` mit
 * `findings.json` und `run.json`; das gehört über „Findings-Datei laden" ins
 * Banner. Hier geht es nur darum, dass die Anwendung auch ohne Engine-Lauf etwas
 * anzuzeigen hat – für die Gestaltung und für die Tests.
 *
 * Läuft vor `npm run dev` und `npm run build`. Die erzeugten Dateien sind
 * Build-Artefakte und liegen unter `data/`, das die `.gitignore` ausschließt.
 *
 * Grundsätze aus CLAUDE.md, die hier gelten:
 *   Regel 2 – Beträge bleiben Strings; es wird nichts in Zahlen gewandelt.
 *   Regel 4 – nichts wird stumm verworfen: jede unvollständige Datei bricht den Lauf ab.
 *   Regel 8 – Meldungen nennen nur Datei, Feld und Regel-ID, nie Geschäftspartnerdaten.
 *   Regel 9 – deterministisch: Reihenfolge nach Dateiname, stabile Ausgabe.
 */
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { load as loadYaml } from 'js-yaml'

const UI_DIR = fileURLToPath(new URL('..', import.meta.url))
// Übersteuerbar, damit sich derselbe Weg später auf `runs/<run_id>/` der Engine
// richten lässt und der Abbruchpfad ohne Eingriff in `logic/` prüfbar ist.
const SOURCE_DIR = process.env.MDQ_FINDINGS_DIR
  ? resolve(process.env.MDQ_FINDINGS_DIR)
  : join(UI_DIR, '..', 'logic', 'examples', 'findings')
const OUT_DIR = join(UI_DIR, 'public', 'data')

/** Pflichtfelder laut `logic/finding.schema.json` (Version 1.1). */
const REQUIRED_TOP_LEVEL = [
  'finding_id', 'run_id', 'rule_id', 'rule_version', 'engine_version', 'pack_version',
  'side', 'category', 'severity', 'damage_class', 'tier', 'action_type', 'title',
  'entity', 'current', 'why', 'if_wrong', 'remediation', 'status', 'data_as_of', 'created_at',
]
const REQUIRED_NESTED = {
  entity: ['bp_key', 'role'],
  current: ['source_table', 'source_field', 'value'],
  remediation: ['sap_transaction', 'mass_change_eligible'],
}
const FINDING_ID_PATTERN = /^F-[a-f0-9]{12}$/
const RULE_ID_PATTERN = /^(AR|AP|CROSS)-(COM|VAL|CON|HYG|RSK|DUP|LEA)-[0-9]{3}$/

/** Bricht den Lauf mit Dateibezug ab – kein stilles Überspringen. */
function fail(file, reason) {
  throw new Error(`${file}: ${reason}`)
}

function checkFinding(file, finding) {
  if (typeof finding !== 'object' || finding === null || Array.isArray(finding)) {
    fail(file, 'kein YAML-Mapping auf oberster Ebene')
  }
  for (const field of REQUIRED_TOP_LEVEL) {
    if (!(field in finding)) fail(file, `Pflichtfeld fehlt: ${field}`)
  }
  for (const [parent, fields] of Object.entries(REQUIRED_NESTED)) {
    const node = finding[parent]
    if (typeof node !== 'object' || node === null) fail(file, `${parent} ist kein Mapping`)
    for (const field of fields) {
      if (!(field in node)) fail(file, `Pflichtfeld fehlt: ${parent}.${field}`)
    }
  }
  if (!FINDING_ID_PATTERN.test(finding.finding_id)) {
    fail(file, 'finding_id passt nicht auf ^F-[a-f0-9]{12}$')
  }
  if (!RULE_ID_PATTERN.test(finding.rule_id)) {
    fail(file, `rule_id passt nicht auf das Regel-Muster: ${finding.rule_id}`)
  }
}

/** Prüft, dass alle Findings zum selben Lauf gehören, und liefert den Wert. */
function singleValue(findings, field) {
  const values = [...new Set(findings.map((entry) => entry.finding[field]))]
  if (values.length !== 1) {
    const files = findings.map((entry) => entry.file).join(', ')
    throw new Error(
      `Uneinheitliches Feld ${field} über die Findings (${values.join(' | ')}) in: ${files}`,
    )
  }
  return values[0]
}

function main() {
  let files
  try {
    files = readdirSync(SOURCE_DIR).filter((name) => name.endsWith('.yaml')).sort()
  } catch (error) {
    throw new Error(`Beispiel-Findings nicht lesbar unter ${SOURCE_DIR}: ${error.message}`)
  }
  if (files.length === 0) throw new Error(`Keine *.yaml unter ${SOURCE_DIR}`)

  const entries = files.map((file) => {
    let finding
    try {
      finding = loadYaml(readFileSync(join(SOURCE_DIR, file), 'utf8'))
    } catch (error) {
      fail(file, `YAML nicht lesbar: ${error.message}`)
    }
    checkFinding(file, finding)
    return { file, finding }
  })

  const seen = new Map()
  for (const { file, finding } of entries) {
    if (seen.has(finding.finding_id)) {
      fail(file, `finding_id doppelt, schon in ${seen.get(finding.finding_id)}`)
    }
    seen.set(finding.finding_id, file)
  }

  const findings = entries.map((entry) => entry.finding)
  const companyCodes = [
    ...new Set(findings.map((finding) => finding.entity.company_code).filter((code) => code != null)),
  ].sort()

  const run = {
    run_id: singleValue(entries, 'run_id'),
    data_as_of: singleValue(entries, 'data_as_of'),
    engine_version: singleValue(entries, 'engine_version'),
    pack_version: singleValue(entries, 'pack_version'),
    // Ausdrücklich 0: hier lief keine Engine, es wurde keine Tabelle geladen.
    // Das Banner blendet die Angabe bei 0 aus, statt eine Zahl zu erfinden. Die
    // echte Zahl steht in `runs/<run_id>/run.json` und kommt nur von dort.
    tables_loaded: 0,
    // Ebenso eine Ableitung, kein Laufumfang: die Buchungskreise stammen aus den
    // sechs Beispielen. `run.json` der Engine nennt stattdessen die des Laufs –
    // einschließlich der Buchungskreise ohne Befund.
    company_codes: companyCodes,
  }

  mkdirSync(OUT_DIR, { recursive: true })
  writeFileSync(join(OUT_DIR, 'findings.json'), `${JSON.stringify(findings, null, 2)}\n`, 'utf8')
  writeFileSync(join(OUT_DIR, 'run.json'), `${JSON.stringify(run, null, 2)}\n`, 'utf8')

  console.log(
    `${findings.length} Findings aus ${files.length} Dateien -> public/data/findings.json ` +
      `(Lauf ${run.run_id}, Datenstand ${run.data_as_of}, ` +
      `Buchungskreise ${companyCodes.join(', ') || 'keine'})`,
  )
}

try {
  main()
} catch (error) {
  console.error(`build-data: ${error.message}`)
  process.exit(1)
}
