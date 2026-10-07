import { apiFetch } from './client'
import type {
  Incident,
  IncidentDetail,
  IncidentListResponse,
  IncidentOutcome,
  IncidentStatus,
} from './types'

export interface IncidentFilters {
  severity: string[]
  status: string[]
  source: string[]
  language: string[]
  vipId: string[]
  assigneeId: string[]
  threatType: string[]
  createdFrom: string | null
  createdTo: string | null
  includeMerged: boolean
}

export const EMPTY_FILTERS: IncidentFilters = {
  severity: [],
  status: [],
  source: [],
  language: [],
  vipId: [],
  assigneeId: [],
  threatType: [],
  createdFrom: null,
  createdTo: null,
  includeMerged: false,
}

export type IncidentSort = 'time' | 'severity'

export function buildIncidentQuery(
  filters: IncidentFilters,
  sort: IncidentSort,
  cursor?: string | null,
  limit?: number,
): string {
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
  params.set('sort', sort)
  if (cursor) {
    params.set('cursor', cursor)
  }
  if (limit) {
    params.set('limit', String(limit))
  }
  return params.toString()
}

export async function fetchIncidents(
  filters: IncidentFilters,
  sort: IncidentSort,
  cursor?: string | null,
): Promise<IncidentListResponse> {
  return apiFetch<IncidentListResponse>(`/incidents?${buildIncidentQuery(filters, sort, cursor)}`)
}

export async function fetchIncident(incidentId: string): Promise<IncidentDetail> {
  return apiFetch<IncidentDetail>(`/incidents/${incidentId}`)
}

export async function changeStatus(
  incidentId: string,
  status: IncidentStatus,
  options: { reason?: string; outcome?: IncidentOutcome } = {},
): Promise<Incident> {
  return apiFetch<Incident>(`/incidents/${incidentId}/status`, {
    method: 'POST',
    body: { status, reason: options.reason ?? null, outcome: options.outcome ?? null },
  })
}

export async function assignIncident(incidentId: string, assigneeId: string): Promise<Incident> {
  return apiFetch<Incident>(`/incidents/${incidentId}/assign`, {
    method: 'POST',
    body: { assignee_id: assigneeId },
  })
}

export async function addNote(incidentId: string, body: string) {
  return apiFetch(`/incidents/${incidentId}/notes`, { method: 'POST', body: { body } })
}
