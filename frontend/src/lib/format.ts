import type { IncidentEventType, IncidentOutcome, IncidentStatus, Severity, UserRole } from '../api/types'

export const SEVERITY_STYLES: Record<Severity, string> = {
  critical: 'bg-red-600 text-white',
  high: 'bg-orange-500 text-white',
  medium: 'bg-amber-400 text-slate-900',
  low: 'bg-slate-300 text-slate-800',
}

export const SEVERITY_TEXT: Record<Severity, string> = {
  critical: 'text-red-600',
  high: 'text-orange-500',
  medium: 'text-amber-600',
  low: 'text-slate-500',
}

export const STATUS_LABELS: Record<IncidentStatus, string> = {
  new: 'New',
  under_review: 'Under review',
  escalated: 'Escalated',
  resolved: 'Resolved',
  false_positive: 'False positive',
}

export const STATUS_STYLES: Record<IncidentStatus, string> = {
  new: 'bg-blue-100 text-blue-800',
  under_review: 'bg-indigo-100 text-indigo-800',
  escalated: 'bg-red-100 text-red-800',
  resolved: 'bg-emerald-100 text-emerald-800',
  false_positive: 'bg-slate-200 text-slate-700',
}

export const OUTCOME_LABELS: Record<IncidentOutcome, string> = {
  reported_to_platform: 'Reported to platform',
  taken_down: 'Taken down',
  referred_to_authorities: 'Referred to authorities',
  no_action_needed: 'No action needed',
  below_threshold: 'Below threshold',
}

export const EVENT_LABELS: Record<IncidentEventType, string> = {
  status_change: 'Status changed',
  assign: 'Assigned',
  note: 'Note added',
  severity_override: 'Severity overridden',
  rescore: 'Re-scored',
  item_attached: 'Item attached',
  merged_into: 'Merged',
  campaign_linked: 'Campaign linked',
}

export const ROLE_LABELS: Record<UserRole, string> = {
  admin: 'Admin',
  lead: 'Lead',
  analyst: 'Analyst',
  viewer: 'Viewer',
}

export function canEditIncidents(role: UserRole | null): boolean {
  return role === 'analyst' || role === 'lead' || role === 'admin'
}

export function canReopenIncidents(role: UserRole | null): boolean {
  return role === 'lead' || role === 'admin'
}

export function canManageVips(role: UserRole | null): boolean {
  return role === 'lead' || role === 'admin'
}

const ALLOWED_TRANSITIONS: Record<IncidentStatus, IncidentStatus[]> = {
  new: ['under_review'],
  under_review: ['escalated', 'resolved', 'false_positive'],
  escalated: ['resolved', 'false_positive'],
  resolved: ['under_review'],
  false_positive: ['under_review'],
}

export function allowedTransitions(status: IncidentStatus, role: UserRole | null): IncidentStatus[] {
  const allowed = ALLOWED_TRANSITIONS[status] ?? []
  if (status === 'resolved' || status === 'false_positive') {
    return canReopenIncidents(role) ? allowed : []
  }
  return canEditIncidents(role) ? allowed : []
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return '—'
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

export function timeAgo(value: string): string {
  const seconds = Math.round((Date.now() - new Date(value).getTime()) / 1000)
  if (seconds < 60) {
    return 'just now'
  }
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) {
    return `${minutes}m ago`
  }
  const hours = Math.round(minutes / 60)
  if (hours < 24) {
    return `${hours}h ago`
  }
  return `${Math.round(hours / 24)}d ago`
}

export function formatBytes(size: number): string {
  if (size < 1024) {
    return `${size} B`
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}
