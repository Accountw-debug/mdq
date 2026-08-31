import type { RefObject } from 'react'
import { SearchIcon, XIcon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  CATEGORY_LABELS,
  SEVERITY_LABELS,
  SIDE_LABELS,
  STATUS_LABELS,
  TIER_LABELS,
} from '@/lib/labels'
import type { Filters } from '@/lib/select-findings'
import { ALL, NO_COMPANY_CODE } from '@/lib/select-findings'
import { CATEGORIES, SEVERITIES, SIDES, STATUSES, TIERS } from '@/types/finding'

/**
 * Filterleiste des Explorers: sechs einwertige Filter plus Volltextsuche.
 *
 * Einwertig heißt: je Dimension ein Wert oder „Alle". Die Dimensionen wirken
 * miteinander als UND. Das reicht für die Fragen der Buchhalter („zeig mir die
 * kritischen Kreditoren in 2000") und hält die Leiste ruhig.
 */

interface Option {
  value: string
  label: string
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: readonly Option[]
  onChange: (value: string) => void
}) {
  return (
    <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
      {label}
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger size="sm" className="min-w-28 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>Alle</SelectItem>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </label>
  )
}

function toOptions<T extends string>(
  values: readonly T[],
  labels: Record<T, string>,
): readonly Option[] {
  return values.map((value) => ({ value, label: labels[value] }))
}

export function FilterBar({
  filters,
  search,
  companyCodes,
  hasActive,
  searchRef,
  onFilterChange,
  onSearchChange,
  onReset,
}: {
  filters: Filters
  search: string
  companyCodes: readonly string[]
  hasActive: boolean
  searchRef: RefObject<HTMLInputElement | null>
  onFilterChange: (key: keyof Filters, value: string) => void
  onSearchChange: (search: string) => void
  onReset: () => void
}) {
  const companyCodeOptions: Option[] = companyCodes.map((code) => ({
    value: code,
    label: code === NO_COMPANY_CODE ? 'ohne Buchungskreis' : code,
  }))

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <div className="relative">
        <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          ref={searchRef}
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Suchen …"
          aria-label="Suche über Geschäftspartner, Titel und Regel-ID"
          className="h-7 w-64 pl-8 text-xs"
        />
        {search === '' && (
          <kbd className="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 font-mono text-[0.65rem] text-muted-foreground">
            /
          </kbd>
        )}
      </div>

      <FilterSelect
        label="Seite"
        value={filters.side}
        options={toOptions(SIDES, SIDE_LABELS)}
        onChange={(value) => onFilterChange('side', value)}
      />
      <FilterSelect
        label="Kategorie"
        value={filters.category}
        options={toOptions(CATEGORIES, CATEGORY_LABELS)}
        onChange={(value) => onFilterChange('category', value)}
      />
      <FilterSelect
        label="Schwere"
        value={filters.severity}
        options={toOptions(SEVERITIES, SEVERITY_LABELS)}
        onChange={(value) => onFilterChange('severity', value)}
      />
      <FilterSelect
        label="Stufe"
        value={filters.tier}
        options={toOptions(TIERS, TIER_LABELS)}
        onChange={(value) => onFilterChange('tier', value)}
      />
      <FilterSelect
        label="Buchungskreis"
        value={filters.companyCode}
        options={companyCodeOptions}
        onChange={(value) => onFilterChange('companyCode', value)}
      />
      <FilterSelect
        label="Status"
        value={filters.status}
        options={toOptions(STATUSES, STATUS_LABELS)}
        onChange={(value) => onFilterChange('status', value)}
      />

      {hasActive && (
        <Button variant="ghost" size="xs" onClick={onReset}>
          <XIcon data-icon="inline-start" />
          Filter zurücksetzen
        </Button>
      )}
    </div>
  )
}
