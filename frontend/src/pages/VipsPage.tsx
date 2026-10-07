import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { ApiError } from '../api/client'
import { createVip, fetchVips } from '../api/vips'
import type { Sensitivity } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { canManageVips, formatDateTime } from '../lib/format'

export function VipsPage() {
  const { role } = useAuth()
  const queryClient = useQueryClient()
  const canManage = canManageVips(role)

  const [name, setName] = useState('')
  const [sensitivity, setSensitivity] = useState<Sensitivity>('normal')
  const [error, setError] = useState<string | null>(null)

  const vipsQuery = useQuery({ queryKey: ['vips'], queryFn: fetchVips })

  const createMutation = useMutation({
    mutationFn: () => createVip({ name: name.trim(), sensitivity, monitoring_active: true }),
    onSuccess: async () => {
      setName('')
      setSensitivity('normal')
      setError(null)
      await queryClient.invalidateQueries({ queryKey: ['vips'] })
    },
    onError: (caught) => setError(caught instanceof ApiError ? caught.detail : 'Could not create the VIP'),
  })

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (name.trim()) {
      createMutation.mutate()
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">VIPs</h1>

      {canManage ? (
        <form onSubmit={submit} className="flex flex-wrap items-end gap-3 rounded-lg bg-white p-4 shadow-sm">
          <div>
            <label className="block text-sm font-medium" htmlFor="vip-name">
              Name
            </label>
            <input
              id="vip-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="mt-1 rounded border border-slate-300 px-3 py-2"
              placeholder="e.g. Asha Verma"
            />
          </div>
          <div>
            <label className="block text-sm font-medium" htmlFor="vip-sensitivity">
              Sensitivity
            </label>
            <select
              id="vip-sensitivity"
              value={sensitivity}
              onChange={(event) => setSensitivity(event.target.value as Sensitivity)}
              className="mt-1 rounded border border-slate-300 bg-white px-3 py-2"
            >
              <option value="low">low</option>
              <option value="normal">normal</option>
              <option value="high">high</option>
            </select>
          </div>
          <button
            type="submit"
            disabled={createMutation.isPending || name.trim().length === 0}
            className="rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-50"
          >
            Add VIP
          </button>
          {error ? (
            <p role="alert" className="w-full text-sm text-red-600">
              {error}
            </p>
          ) : null}
        </form>
      ) : null}

      {vipsQuery.isLoading ? <p className="text-sm text-slate-500">Loading VIPs…</p> : null}
      {vipsQuery.isError ? (
        <p role="alert" className="text-sm text-red-600">
          Could not load VIPs.
        </p>
      ) : null}

      <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {(vipsQuery.data ?? []).map((vip) => (
          <li key={vip.id}>
            <Link
              to={`/vips/${vip.id}`}
              className="block rounded-lg border border-slate-200 bg-white p-4 shadow-sm hover:border-slate-300"
            >
              <div className="flex items-center gap-2">
                <span className="font-medium">{vip.name}</span>
                <span
                  className={`rounded px-2 py-0.5 text-xs ${
                    vip.monitoring_active ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-600'
                  }`}
                >
                  {vip.monitoring_active ? 'monitoring' : 'paused'}
                </span>
              </div>
              <p className="mt-2 text-xs text-slate-500">
                sensitivity: {vip.sensitivity} · config v{vip.config_version}
              </p>
              <p className="text-xs text-slate-400">created {formatDateTime(vip.created_at)}</p>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}
