import { useEffect, useState } from 'react'
import { Key } from '@/components/Key'
import { formatDate } from '@/lib/format'
import type { Finding, RunInfo } from '@/types/finding'

/**
 * Aufgabe 1: nur der Nachweis, dass die Daten ankommen. Layout, Datenstand-Banner
 * und Findings-Explorer folgen in Aufgabe 2 (docs/specs/SPRINT-5-UI.md).
 */

interface LoadedRun {
  run: RunInfo
  findings: Finding[]
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`)
  return (await response.json()) as T
}

async function loadRun(): Promise<LoadedRun> {
  const [run, findings] = await Promise.all([
    fetchJson<RunInfo>('data/run.json'),
    fetchJson<Finding[]>('data/findings.json'),
  ])
  return { run, findings }
}

function App() {
  const [data, setData] = useState<LoadedRun | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    loadRun()
      .then((loaded) => active && setData(loaded))
      .catch((cause: unknown) => active && setError(String(cause)))
    return () => {
      active = false
    }
  }, [])

  if (error) {
    return (
      <main className="p-8">
        <p className="text-destructive">Findings konnten nicht geladen werden: {error}</p>
      </main>
    )
  }

  if (!data) {
    return (
      <main className="p-8">
        <p className="text-muted-foreground">Findings werden geladen …</p>
      </main>
    )
  }

  const { run, findings } = data

  return (
    <main className="p-8">
      <p className="text-2xl">{findings.length} Findings geladen</p>
      <p className="text-muted-foreground mt-2 text-sm">
        Stand {formatDate(run.data_as_of)} · Lauf <Key>{run.run_id}</Key> · Engine{' '}
        {run.engine_version} · Regelpaket {run.pack_version} · Buchungskreise{' '}
        {run.company_codes.length === 0
          ? 'keine'
          : run.company_codes.map((code, index) => (
              <span key={code}>
                {index > 0 ? ', ' : ''}
                <Key>{code}</Key>
              </span>
            ))}
      </p>
    </main>
  )
}

export default App
