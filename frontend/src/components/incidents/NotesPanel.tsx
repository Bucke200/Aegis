import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'

import { ApiError } from '../../api/client'
import { addNote } from '../../api/incidents'
import type { IncidentNote } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import { canEditIncidents, formatDateTime } from '../../lib/format'

export function NotesPanel({
  incidentId,
  notes,
  userNames,
}: {
  incidentId: string
  notes: IncidentNote[]
  userNames: Map<string, string>
}) {
  const { role } = useAuth()
  const queryClient = useQueryClient()
  const [body, setBody] = useState('')
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: (text: string) => addNote(incidentId, text),
    onSuccess: async () => {
      setBody('')
      setError(null)
      await queryClient.invalidateQueries({ queryKey: ['incident', incidentId] })
    },
    onError: (caught) => setError(caught instanceof ApiError ? caught.detail : 'Could not add the note'),
  })

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (body.trim()) {
      mutation.mutate(body.trim())
    }
  }

  return (
    <div className="space-y-3">
      <ul className="space-y-2">
        {notes.length === 0 ? <li className="text-sm text-slate-500">No notes yet.</li> : null}
        {notes.map((note) => (
          <li key={note.id} data-testid="note" className="rounded border border-slate-200 p-3">
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <span className="font-medium text-slate-700">
                {note.author_id ? (userNames.get(note.author_id) ?? 'Analyst') : 'System'}
              </span>
              <span>{formatDateTime(note.created_at)}</span>
            </div>
            <p className="mt-1 whitespace-pre-wrap text-sm text-slate-800">{note.body}</p>
          </li>
        ))}
      </ul>

      {canEditIncidents(role) ? (
        <form onSubmit={submit} className="space-y-2">
          <label className="block text-sm font-medium" htmlFor="note-body">
            Add a note
          </label>
          <textarea
            id="note-body"
            value={body}
            onChange={(event) => setBody(event.target.value)}
            rows={3}
            className="w-full rounded border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            type="submit"
            disabled={mutation.isPending || body.trim().length === 0}
            className="rounded bg-slate-800 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            Add note
          </button>
          {error ? (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          ) : null}
        </form>
      ) : null}
    </div>
  )
}
