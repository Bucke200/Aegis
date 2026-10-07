import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { changeStatus } from '../../api/incidents'
import { ApiError } from '../../api/client'
import type { Incident, IncidentOutcome, IncidentStatus } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import { allowedTransitions, OUTCOME_LABELS, STATUS_LABELS } from '../../lib/format'

const OUTCOMES: IncidentOutcome[] = [
  'reported_to_platform',
  'taken_down',
  'referred_to_authorities',
  'no_action_needed',
]

export function StatusControls({ incident }: { incident: Incident }) {
  const { role } = useAuth()
  const queryClient = useQueryClient()
  const [resolveOpen, setResolveOpen] = useState(false)
  const [reopenOpen, setReopenOpen] = useState(false)
  const [outcome, setOutcome] = useState<IncidentOutcome>('reported_to_platform')
  const [reason, setReason] = useState('')
  const [confirmFalsePositive, setConfirmFalsePositive] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: (variables: { status: IncidentStatus; reason?: string; outcome?: IncidentOutcome }) =>
      changeStatus(incident.id, variables.status, { reason: variables.reason, outcome: variables.outcome }),
    onSuccess: async () => {
      setResolveOpen(false)
      setReopenOpen(false)
      setConfirmFalsePositive(false)
      setReason('')
      setError(null)
      await queryClient.invalidateQueries({ queryKey: ['incident', incident.id] })
      await queryClient.invalidateQueries({ queryKey: ['incidents'] })
    },
    onError: (caught) => {
      setError(caught instanceof ApiError ? caught.detail : 'Could not change status')
    },
  })

  if (incident.merged_into_id) {
    return (
      <p className="rounded bg-slate-100 p-3 text-sm text-slate-500">
        This item incident is merged; work continues on the account incident.
      </p>
    )
  }

  const transitions = allowedTransitions(incident.status, role)
  if (transitions.length === 0) {
    return <p className="text-sm text-slate-500">No status actions are available for your role.</p>
  }

  const activate = (status: IncidentStatus) => {
    if (status === 'resolved') {
      setResolveOpen(true)
      return
    }
    if (status === 'under_review' && (incident.status === 'resolved' || incident.status === 'false_positive')) {
      setReopenOpen(true)
      return
    }
    if (status === 'false_positive') {
      if (!confirmFalsePositive) {
        setConfirmFalsePositive(true)
        setError('Click again to mark this incident as a false positive (this creates a label).')
        return
      }
    }
    mutation.mutate({ status })
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {transitions.map((status) => (
          <button
            key={status}
            type="button"
            disabled={mutation.isPending}
            onClick={() => activate(status)}
            className={
              status === 'resolved'
                ? 'rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50'
                : status === 'false_positive'
                  ? 'rounded border border-slate-400 px-3 py-1.5 text-sm text-slate-700 disabled:opacity-50'
                  : 'rounded bg-slate-800 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50'
            }
          >
            {status === 'under_review' && incident.status !== 'new'
              ? 'Reopen'
              : status === 'false_positive'
                ? 'False positive'
                : STATUS_LABELS[status]}
          </button>
        ))}
      </div>
      {error ? (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      ) : null}

      {resolveOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
            <h2 className="text-lg font-semibold">Resolve incident</h2>
            <label className="mt-4 block text-sm font-medium" htmlFor="outcome">
              Outcome
            </label>
            <select
              id="outcome"
              value={outcome}
              onChange={(event) => setOutcome(event.target.value as IncidentOutcome)}
              className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
            >
              {OUTCOMES.map((value) => (
                <option key={value} value={value}>
                  {OUTCOME_LABELS[value]}
                </option>
              ))}
            </select>
            <label className="mt-3 block text-sm font-medium" htmlFor="resolve-reason">
              Reason (optional)
            </label>
            <textarea
              id="resolve-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              rows={3}
              className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
            />
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                className="rounded border border-slate-300 px-3 py-1.5 text-sm"
                onClick={() => setResolveOpen(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={mutation.isPending}
                className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                onClick={() => mutation.mutate({ status: 'resolved', outcome, reason: reason || undefined })}
              >
                Resolve
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {reopenOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
            <h2 className="text-lg font-semibold">Reopen incident</h2>
            <label className="mt-4 block text-sm font-medium" htmlFor="reopen-reason">
              Reason
            </label>
            <textarea
              id="reopen-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              rows={3}
              className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
            />
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                className="rounded border border-slate-300 px-3 py-1.5 text-sm"
                onClick={() => setReopenOpen(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={mutation.isPending || reason.trim().length === 0}
                className="rounded bg-slate-800 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                onClick={() => mutation.mutate({ status: 'under_review', reason })}
              >
                Reopen
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
