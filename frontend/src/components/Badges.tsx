import type { ReactNode } from 'react'

import type { IncidentStatus, Severity } from '../api/types'
import { SEVERITY_STYLES, STATUS_LABELS, STATUS_STYLES } from '../lib/format'

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span
      data-testid="severity-badge"
      className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${SEVERITY_STYLES[severity]}`}
    >
      {severity}
    </span>
  )
}

export function StatusBadge({ status }: { status: IncidentStatus }) {
  return (
    <span
      data-testid="status-badge"
      className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[status]}`}
    >
      {STATUS_LABELS[status]}
    </span>
  )
}

export function Chip({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full bg-slate-200 px-2 py-0.5 text-xs text-slate-700">
      {children}
    </span>
  )
}
