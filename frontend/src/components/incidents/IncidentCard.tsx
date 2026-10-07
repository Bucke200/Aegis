import { Link } from 'react-router-dom'

import type { Incident } from '../../api/types'
import { timeAgo } from '../../lib/format'
import { Chip, SeverityBadge, StatusBadge } from '../Badges'

interface IncidentCardProps {
  incident: Incident
  vipNames: Map<string, string>
}

export function IncidentCard({ incident, vipNames }: IncidentCardProps) {
  const vipLabels = incident.vip_ids.map((vipId) => vipNames.get(vipId) ?? vipId.slice(0, 8))
  const isAccount = incident.subject_type === 'account'
  const snippet = isAccount
    ? `${incident.account?.display_name ?? 'Unknown'} · @${incident.account?.handle ?? 'unknown'}`
    : (incident.item?.text ?? 'No text content')

  return (
    <Link
      to={`/incidents/${incident.id}`}
      data-testid="incident-card"
      className="block rounded-lg border border-slate-200 bg-white p-4 shadow-sm transition hover:border-slate-300 hover:shadow"
    >
      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge severity={incident.severity} />
        <StatusBadge status={incident.status} />
        <span className="text-xs text-slate-500">risk {incident.risk_score.toFixed(2)}</span>
        <span className="ml-auto text-xs text-slate-500" title={new Date(incident.created_at).toLocaleString()}>
          {timeAgo(incident.created_at)}
        </span>
      </div>

      <p className="mt-3 line-clamp-2 text-sm text-slate-800">{snippet}</p>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        {isAccount ? <Chip>account incident</Chip> : null}
        {incident.threat_types.map((threat) => (
          <Chip key={threat}>{threat.replace(/_/g, ' ')}</Chip>
        ))}
        {vipLabels.map((label) => (
          <Chip key={label}>VIP: {label}</Chip>
        ))}
      </div>

      {incident.explanation ? (
        <p className="mt-2 text-xs text-slate-500">{incident.explanation}</p>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-500">
        <span>{incident.source}</span>
        {incident.language ? <span>{incident.language}</span> : null}
        <span>assignee: {incident.assignee?.display_name ?? incident.assignee?.email ?? 'unassigned'}</span>
      </div>
    </Link>
  )
}
