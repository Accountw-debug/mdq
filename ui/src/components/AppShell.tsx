import type { ReactNode } from 'react'
import { BookOpenIcon, LayoutDashboardIcon, ListChecksIcon } from 'lucide-react'
import { DataBanner } from '@/components/DataBanner'
import { TooltipProvider } from '@/components/ui/tooltip'
import type { LoadedRun } from '@/lib/load-run'
import { cn } from '@/lib/utils'

/**
 * App-Rahmen: schmale linke Navigation, Datenstand-Banner, Inhalt.
 *
 * Kein Router (Spec Sprint 5) – drei Ansichten reichen, der Zustand bleibt im
 * Speicher. Das Banner steht über dem Inhalt und damit auf jedem Screen.
 */

export type View = 'dashboard' | 'findings' | 'rules'

const NAV: { view: View; label: string; icon: typeof LayoutDashboardIcon }[] = [
  { view: 'dashboard', label: 'Dashboard', icon: LayoutDashboardIcon },
  { view: 'findings', label: 'Findings', icon: ListChecksIcon },
  { view: 'rules', label: 'Regeln', icon: BookOpenIcon },
]

export function AppShell({
  run,
  source,
  onSelectFile,
  loadError,
  view,
  onViewChange,
  children,
}: {
  run: LoadedRun['run']
  source: LoadedRun['source']
  onSelectFile: (file: File) => void
  loadError: string | null
  view: View
  onViewChange: (view: View) => void
  children: ReactNode
}) {
  return (
    <TooltipProvider>
      <div className="flex min-h-svh bg-background text-foreground">
        <nav aria-label="Hauptnavigation" className="w-44 shrink-0 border-r px-3 py-4">
          <div className="px-2 pb-4">
            <div className="text-sm font-semibold tracking-tight">MDQ</div>
            <div className="text-xs text-muted-foreground">Stammdaten-Check</div>
          </div>
          <ul className="flex flex-col gap-0.5">
            {NAV.map((item) => {
              const Icon = item.icon
              const active = item.view === view
              return (
                <li key={item.view}>
                  <button
                    type="button"
                    onClick={() => onViewChange(item.view)}
                    aria-current={active ? 'page' : undefined}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-sm outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50',
                      active
                        ? 'bg-muted font-medium text-foreground'
                        : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground',
                    )}
                  >
                    <Icon className="size-4" />
                    {item.label}
                  </button>
                </li>
              )
            })}
          </ul>
        </nav>

        <div className="flex min-w-0 flex-1 flex-col">
          <DataBanner
            run={run}
            source={source}
            onSelectFile={onSelectFile}
            loadError={loadError}
          />
          <main className="min-w-0 flex-1 p-6">{children}</main>
        </div>
      </div>
    </TooltipProvider>
  )
}

/** Platzhalter für die Screens, die in späteren Aufgaben kommen. */
export function Placeholder({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="rounded-lg border border-dashed p-8">
      <h1 className="text-sm font-medium">{title}</h1>
      <p className="mt-1 text-sm text-muted-foreground">{hint}</p>
    </div>
  )
}
