import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { fetchIncidents, type IncidentFilters, type IncidentSort } from '../api/incidents'
import { fetchDirectory } from '../api/users'
import { fetchVips } from '../api/vips'
import { useAuth } from '../auth/AuthContext'
import { FilterSidebar } from '../components/incidents/FilterSidebar'
import { IncidentCard } from '../components/incidents/IncidentCard'
import { canEditIncidents } from '../lib/format'

function parseFilters(params: URLSearchParams): IncidentFilters {
  return {
    severity: params.getAll('severity'),
    status: params.getAll('status'),
    source: params.getAll('source'),
    language: params.getAll('language'),
    vipId: params.getAll('vip_id'),
    assigneeId: params.getAll('assignee_id'),
    threatType: params.getAll('threat_type'),
    createdFrom: params.get('created_from'),
    createdTo: params.get('created_to'),
    includeMerged: params.get('include_merged') === 'true',
  }
}

function toSearchParams(filters: IncidentFilters, sort: IncidentSort): URLSearchParams {
  const params = new URLSearchParams()
  const repeated: Array<[string, string[]]> = [
    ['severity', filters.severity],
    ['status', filters.status],
    ['source', filters.source],
    ['language', filters.language],
    ['vip_id', filters.vipId],
    ['assignee_id', filters.assigneeId],
    ['threat_type', filters.threatType],
  ]
  for (const [key, values] of repeated) {
    for (const value of values) {
      params.append(key, value)
    }
  }
  if (filters.createdFrom) {
    params.set('created_from', filters.createdFrom)
  }
  if (filters.createdTo) {
    params.set('created_to', filters.createdTo)
  }
  if (filters.includeMerged) {
    params.set('include_merged', 'true')
  }
  if (sort !== 'time') {
    params.set('sort', sort)
  }
  return params
}

export function IncidentsPage() {
  const { role } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const filters = useMemo(() => parseFilters(searchParams), [searchParams])
  const sort: IncidentSort = searchParams.get('sort') === 'severity' ? 'severity' : 'time'

  const vipsQuery = useQuery({ queryKey: ['vips'], queryFn: fetchVips })
  const canAssign = canEditIncidents(role)
  const directoryQuery = useQuery({
    queryKey: ['directory'],
    queryFn: fetchDirectory,
    enabled: canAssign,
  })

  const incidentsQuery = useInfiniteQuery({
    queryKey: ['incidents', filters, sort],
    queryFn: ({ pageParam }) => fetchIncidents(filters, sort, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor,
  })

  const vipNames = useMemo(
    () => new Map((vipsQuery.data ?? []).map((vip) => [vip.id, vip.name])),
    [vipsQuery.data],
  )
  const incidents = useMemo(
    () => (incidentsQuery.data?.pages ?? []).flatMap((page) => page.items),
    [incidentsQuery.data],
  )

  const updateFilters = (next: IncidentFilters) => {
    setSearchParams(toSearchParams(next, sort), { replace: true })
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
      <FilterSidebar
        filters={filters}
        onChange={updateFilters}
        vips={vipsQuery.data ?? []}
        assignees={directoryQuery.data ?? []}
        showAssignees={canAssign}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      <section>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold">Incident feed</h1>
          <span className="text-sm text-slate-500">{incidents.length} loaded</span>
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            className="rounded border border-slate-300 bg-white px-2 py-1 text-xs lg:hidden"
          >
            Filters
          </button>
          <label className="ml-auto flex items-center gap-2 text-sm text-slate-600">
            Sort
            <select
              value={sort}
              onChange={(event) => setSearchParams(toSearchParams(filters, event.target.value as IncidentSort))}
              className="rounded border border-slate-300 bg-white px-2 py-1 text-sm"
            >
              <option value="time">Newest first</option>
              <option value="severity">Severity</option>
            </select>
          </label>
        </div>

        {incidentsQuery.isError ? (
          <p role="alert" className="mt-4 rounded bg-red-50 p-3 text-sm text-red-700">
            Could not load incidents. The list refreshes automatically when the connection recovers.
          </p>
        ) : null}

        <div className="mt-4 space-y-3">
          {incidentsQuery.isLoading ? <p className="text-sm text-slate-500">Loading incidents…</p> : null}
          {!incidentsQuery.isLoading && incidents.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
              No incidents match these filters.
            </div>
          ) : null}
          {incidents.map((incident) => (
            <IncidentCard key={incident.id} incident={incident} vipNames={vipNames} />
          ))}
        </div>

        {incidentsQuery.hasNextPage ? (
          <button
            type="button"
            onClick={() => void incidentsQuery.fetchNextPage()}
            disabled={incidentsQuery.isFetchingNextPage}
            className="mt-4 rounded border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 disabled:opacity-50"
          >
            {incidentsQuery.isFetchingNextPage ? 'Loading…' : 'Load more'}
          </button>
        ) : null}
      </section>
    </div>
  )
}
