import { useQuery } from '@tanstack/react-query'
import { useMemo, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ApiError } from '../api/client'
import { fetchIncident } from '../api/incidents'
import { fetchDirectory } from '../api/users'
import type { EvidenceArtifact, IncidentDetail } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { SeverityBadge, StatusBadge } from '../components/Badges'
import { AssignControl } from '../components/incidents/AssignControl'
import { DetectionPanel } from '../components/incidents/DetectionPanel'
import { HistoryTimeline } from '../components/incidents/HistoryTimeline'
import { NotesPanel } from '../components/incidents/NotesPanel'
import { StatusControls } from '../components/incidents/StatusControls'
import { canEditIncidents, formatBytes, formatDateTime, OUTCOME_LABELS } from '../lib/format'

function EvidenceList({ artifacts }: { artifacts: EvidenceArtifact[] }) {
  if (artifacts.length === 0) {
    return <p className="text-sm text-slate-500">No evidence captured.</p>
  }
  return (
    <ul className="space-y-2">
      {artifacts.map((artifact) => (
        <li key={artifact.id} className="rounded border border-slate-200 p-2 text-xs">
          <p className="font-medium text-slate-700">{artifact.kind}</p>
          <p className="truncate text-slate-500" title={artifact.object_key}>
            {artifact.object_key}
          </p>
          <p className="text-slate-400">
            {formatBytes(artifact.size)} · {formatDateTime(artifact.captured_at)}
          </p>
        </li>
      ))}
    </ul>
  )
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-lg bg-white p-4 shadow-sm">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h2>
      {children}
    </section>
  )
}

export function IncidentDetailPage() {
  const { incidentId = '' } = useParams()
  const { user, role } = useAuth()

  const detailQuery = useQuery({
    queryKey: ['incident', incidentId],
    queryFn: () => fetchIncident(incidentId),
    enabled: Boolean(incidentId),
  })

  const directoryQuery = useQuery({
    queryKey: ['directory'],
    queryFn: fetchDirectory,
    enabled: canEditIncidents(role),
  })

  const userNames = useMemo(() => {
    const names = new Map<string, string>()
    if (user) {
      names.set(user.id, user.display_name ?? user.email)
    }
    for (const entry of directoryQuery.data ?? []) {
      names.set(entry.id, entry.display_name ?? entry.email)
    }
    return names
  }, [directoryQuery.data, user])

  if (detailQuery.isLoading) {
    return <p className="text-sm text-slate-500">Loading incident…</p>
  }
  if (detailQuery.isError) {
    const error = detailQuery.error
    const notFound = error instanceof ApiError && error.status === 404
    return (
      <div className="rounded-lg bg-white p-6 shadow-sm">
        <p className="text-sm text-slate-600">
          {notFound ? 'This incident does not exist or is outside your VIP scope.' : 'Could not load the incident.'}
        </p>
        <Link className="mt-3 inline-block text-sm" to="/incidents">
          Back to the feed
        </Link>
      </div>
    )
  }

  const detail = detailQuery.data as IncidentDetail
  const incident = detail.incident
  const itemText = incident.item?.text ?? null

  return (
    <div className="space-y-6">
      <Link to="/incidents" className="text-sm">
        ← Back to the feed
      </Link>

      <header className="rounded-lg bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center gap-2">
          <SeverityBadge severity={incident.severity} />
          <StatusBadge status={incident.status} />
          <span className="text-xs text-slate-500">
            {incident.subject_type === 'account' ? 'account incident' : 'item incident'} · risk{' '}
            {incident.risk_score.toFixed(2)}
          </span>
          {incident.outcome ? (
            <span className="text-xs text-slate-500">outcome: {OUTCOME_LABELS[incident.outcome]}</span>
          ) : null}
          {incident.below_threshold ? <span className="text-xs text-amber-600">below threshold</span> : null}
          <span className="ml-auto text-xs text-slate-500">
            detected {formatDateTime(incident.created_at)} · updated {formatDateTime(incident.updated_at)}
          </span>
        </div>

        {incident.item?.text ? (
          <p className="mt-4 whitespace-pre-wrap text-sm text-slate-800">{incident.item.text}</p>
        ) : incident.account ? (
          <p className="mt-4 text-sm text-slate-800">
            {incident.account.display_name ?? 'Unknown'} · @{incident.account.handle ?? 'unknown'} (
            {incident.account.source})
          </p>
        ) : null}

        {incident.explanation ? <p className="mt-3 text-xs text-slate-500">{incident.explanation}</p> : null}

        <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-500">
          <span>{incident.source}</span>
          {incident.language ? <span>{incident.language}</span> : null}
          {incident.item?.url ? (
            <a href={incident.item.url} target="_blank" rel="noreferrer noopener">
              Open source
            </a>
          ) : null}
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)]">
        <div className="space-y-6">
          <Panel title="Detections">
            <DetectionPanel detections={detail.detections} itemText={itemText} />
          </Panel>
          <Panel title="Notes">
            <NotesPanel incidentId={incident.id} notes={detail.notes} userNames={userNames} />
          </Panel>
          <Panel title="History">
            <HistoryTimeline events={detail.history} userNames={userNames} />
          </Panel>
        </div>

        <div className="space-y-6">
          <Panel title="Workflow">
            <StatusControls incident={incident} />
            <div className="mt-4 border-t border-slate-200 pt-4">
              <AssignControl incident={incident} />
            </div>
          </Panel>

          <Panel title={incident.subject_type === 'account' ? 'Suspect account' : 'Account'}>
            {detail.account ? (
              <dl className="space-y-1 text-sm text-slate-700">
                <div>
                  <dt className="text-xs text-slate-500">Handle</dt>
                  <dd>@{detail.account.handle ?? 'unknown'}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Display name</dt>
                  <dd>{detail.account.display_name ?? '—'}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Platform</dt>
                  <dd>
                    {detail.account.source} · {detail.account.platform_account_id}
                  </dd>
                </div>
              </dl>
            ) : (
              <p className="text-sm text-slate-500">No account data.</p>
            )}
          </Panel>

          {detail.campaign ? (
            <Panel title="Campaign">
              <dl className="space-y-1 text-sm text-slate-700">
                <div>
                  <dt className="text-xs text-slate-500">Status</dt>
                  <dd>{detail.campaign.status}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Coordination score</dt>
                  <dd>{detail.campaign.coordination_score?.toFixed(2) ?? '—'}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Accounts / items</dt>
                  <dd>
                    {detail.campaign.account_count} / {detail.campaign.item_count}
                  </dd>
                </div>
              </dl>
            </Panel>
          ) : null}

          <Panel title="Evidence">
            <EvidenceList artifacts={detail.evidence} />
          </Panel>
        </div>
      </div>
    </div>
  )
}
