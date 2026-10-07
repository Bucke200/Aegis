import type { IncidentFilters } from '../../api/incidents'
import type { UserSummary, Vip } from '../../api/types'
import { INCIDENT_STATUSES, LANGUAGES, SEVERITIES, SOURCES, THREAT_TYPES } from '../../api/types'
import { STATUS_LABELS } from '../../lib/format'

interface FilterSidebarProps {
  filters: IncidentFilters
  onChange: (filters: IncidentFilters) => void
  vips: Vip[]
  assignees: UserSummary[]
  showAssignees: boolean
  open: boolean
  onClose: () => void
}

function FilterGroup({
  title,
  options,
  selected,
  onToggle,
}: {
  title: string
  options: Array<{ value: string; label: string }>
  selected: string[]
  onToggle: (value: string) => void
}) {
  return (
    <fieldset className="border-t border-slate-200 pt-4">
      <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</legend>
      <div className="space-y-1">
        {options.map((option) => (
          <label key={option.value} className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={selected.includes(option.value)}
              onChange={() => onToggle(option.value)}
              className="h-4 w-4 rounded border-slate-300"
            />
            {option.label}
          </label>
        ))}
      </div>
    </fieldset>
  )
}

export function FilterSidebar({
  filters,
  onChange,
  vips,
  assignees,
  showAssignees,
  open,
  onClose,
}: FilterSidebarProps) {
  const toggle = (key: keyof IncidentFilters, value: string) => {
    const current = filters[key]
    if (!Array.isArray(current)) {
      return
    }
    const next = current.includes(value) ? current.filter((item) => item !== value) : [...current, value]
    onChange({ ...filters, [key]: next })
  }

  const panel = (
    <div className="space-y-4">
      <div className="flex items-center justify-between lg:hidden">
        <h2 className="text-sm font-semibold">Filters</h2>
        <button type="button" onClick={onClose} className="rounded border border-slate-300 px-2 py-1 text-xs">
          Close
        </button>
      </div>

      <FilterGroup
        title="Severity"
        options={SEVERITIES.map((severity) => ({ value: severity, label: severity }))}
        selected={filters.severity}
        onToggle={(value) => toggle('severity', value)}
      />
      <FilterGroup
        title="Status"
        options={INCIDENT_STATUSES.map((status) => ({ value: status, label: STATUS_LABELS[status] }))}
        selected={filters.status}
        onToggle={(value) => toggle('status', value)}
      />
      <FilterGroup
        title="Threat type"
        options={THREAT_TYPES.map((threat) => ({ value: threat, label: threat.replace(/_/g, ' ') }))}
        selected={filters.threatType}
        onToggle={(value) => toggle('threatType', value)}
      />
      <FilterGroup
        title="VIP"
        options={vips.map((vip) => ({ value: vip.id, label: vip.name }))}
        selected={filters.vipId}
        onToggle={(value) => toggle('vipId', value)}
      />
      <FilterGroup
        title="Platform"
        options={SOURCES.map((source) => ({ value: source, label: source }))}
        selected={filters.source}
        onToggle={(value) => toggle('source', value)}
      />
      <FilterGroup
        title="Language"
        options={LANGUAGES.map((language) => ({ value: language, label: language }))}
        selected={filters.language}
        onToggle={(value) => toggle('language', value)}
      />
      {showAssignees ? (
        <FilterGroup
          title="Assignee"
          options={assignees.map((user) => ({
            value: user.id,
            label: user.display_name ?? user.email,
          }))}
          selected={filters.assigneeId}
          onToggle={(value) => toggle('assigneeId', value)}
        />
      ) : null}

      <fieldset className="border-t border-slate-200 pt-4">
        <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Created</legend>
        <label className="block text-xs text-slate-500" htmlFor="created-from">
          From
        </label>
        <input
          id="created-from"
          type="date"
          value={filters.createdFrom ?? ''}
          onChange={(event) => onChange({ ...filters, createdFrom: event.target.value || null })}
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
        />
        <label className="mt-2 block text-xs text-slate-500" htmlFor="created-to">
          To
        </label>
        <input
          id="created-to"
          type="date"
          value={filters.createdTo ?? ''}
          onChange={(event) => onChange({ ...filters, createdTo: event.target.value || null })}
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
        />
      </fieldset>

      <label className="flex items-center gap-2 border-t border-slate-200 pt-4 text-sm text-slate-700">
        <input
          type="checkbox"
          checked={filters.includeMerged}
          onChange={(event) => onChange({ ...filters, includeMerged: event.target.checked })}
          className="h-4 w-4 rounded border-slate-300"
        />
        Include merged
      </label>
    </div>
  )

  return (
    <>
      <aside className="hidden rounded-lg bg-white p-4 shadow-sm lg:block">
        <h2 className="mb-4 text-sm font-semibold">Filters</h2>
        {panel}
      </aside>
      {open ? (
        <div className="fixed inset-0 z-50 flex bg-slate-900/40 lg:hidden" onClick={onClose}>
          <div
            className="h-full w-80 max-w-full overflow-y-auto bg-white p-4"
            onClick={(event) => event.stopPropagation()}
          >
            {panel}
          </div>
        </div>
      ) : null}
    </>
  )
}
