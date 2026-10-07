import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { ApiError } from '../../api/client'
import { assignIncident } from '../../api/incidents'
import { fetchDirectory } from '../../api/users'
import type { Incident, UserSummary } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import { canEditIncidents } from '../../lib/format'

export function AssignControl({ incident }: { incident: Incident }) {
  const { role } = useAuth()
  const queryClient = useQueryClient()
  const canAssign = canEditIncidents(role)
  const [selection, setSelection] = useState(incident.assignee_id ?? '')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setSelection(incident.assignee_id ?? '')
  }, [incident.assignee_id])

  const directoryQuery = useQuery({
    queryKey: ['directory'],
    queryFn: fetchDirectory,
    enabled: canAssign,
  })

  const mutation = useMutation({
    mutationFn: (assigneeId: string) => assignIncident(incident.id, assigneeId),
    onSuccess: async () => {
      setError(null)
      await queryClient.invalidateQueries({ queryKey: ['incident', incident.id] })
      await queryClient.invalidateQueries({ queryKey: ['incidents'] })
    },
    onError: (caught) => setError(caught instanceof ApiError ? caught.detail : 'Could not assign'),
  })

  if (incident.merged_into_id) {
    return null
  }

  if (!canAssign) {
    return (
      <p className="text-sm text-slate-600">
        Assignee: {incident.assignee?.display_name ?? incident.assignee?.email ?? 'unassigned'}
      </p>
    )
  }

  const assignees: UserSummary[] = directoryQuery.data ?? []

  return (
    <div className="space-y-2">
      <label className="block text-sm font-medium" htmlFor="assignee">
        Assignee
      </label>
      <div className="flex gap-2">
        <select
          id="assignee"
          value={selection}
          onChange={(event) => setSelection(event.target.value)}
          className="min-w-0 flex-1 rounded border border-slate-300 bg-white px-2 py-1.5 text-sm"
        >
          <option value="">Unassigned</option>
          {assignees.map((user) => (
            <option key={user.id} value={user.id}>
              {user.display_name ?? user.email}
            </option>
          ))}
        </select>
        <button
          type="button"
          disabled={!selection || mutation.isPending}
          onClick={() => mutation.mutate(selection)}
          className="rounded bg-slate-800 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          Assign
        </button>
      </div>
      {error ? (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      ) : null}
    </div>
  )
}
