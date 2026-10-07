import type { IncidentEvent } from '../../api/types'
import { EVENT_LABELS, formatDateTime } from '../../lib/format'

function valueSummary(value: Record<string, unknown> | null): string {
  if (!value) {
    return ''
  }
  return Object.entries(value)
    .filter(([, entry]) => entry !== null && entry !== undefined && entry !== '')
    .map(([key, entry]) => `${key}: ${String(entry)}`)
    .join(', ')
}

export function HistoryTimeline({
  events,
  userNames,
}: {
  events: IncidentEvent[]
  userNames: Map<string, string>
}) {
  if (events.length === 0) {
    return <p className="text-sm text-slate-500">No history yet.</p>
  }
  return (
    <ol className="space-y-3">
      {events.map((event) => {
        const from = valueSummary(event.from_value)
        const to = valueSummary(event.to_value)
        return (
          <li key={event.id} data-testid="history-event" className="flex gap-3">
            <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-slate-400" />
            <div className="min-w-0">
              <p className="text-sm font-medium text-slate-800">
                {EVENT_LABELS[event.event_type] ?? event.event_type}
                {event.actor_id ? (
                  <span className="ml-2 text-xs font-normal text-slate-500">
                    by {userNames.get(event.actor_id) ?? 'user'}
                  </span>
                ) : null}
              </p>
              {from || to ? (
                <p className="text-xs text-slate-500">
                  {from ? `from ${from}` : ''}
                  {from && to ? ' → ' : ''}
                  {to ? `to ${to}` : ''}
                </p>
              ) : null}
              {event.reason ? <p className="text-xs text-slate-500">reason: {event.reason}</p> : null}
              <p className="text-xs text-slate-400">{formatDateTime(event.at)}</p>
            </div>
          </li>
        )
      })}
    </ol>
  )
}
