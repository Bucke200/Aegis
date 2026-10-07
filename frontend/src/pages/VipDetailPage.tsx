import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ApiError } from '../api/client'
import {
  createAlias,
  createContextKeyword,
  createFingerprint,
  createOfficialAccount,
  deleteAlias,
  deleteContextKeyword,
  deleteFingerprint,
  deleteOfficialAccount,
  deleteReferenceMedia,
  fetchAliases,
  fetchContextKeywords,
  fetchFingerprints,
  fetchOfficialAccounts,
  fetchReferenceMedia,
  fetchVip,
  updateVip,
  uploadReferenceMedia,
} from '../api/vips'
import type {
  AliasKind,
  FingerprintKind,
  ReferenceMediaKind,
  Sensitivity,
  Source,
  Vip,
} from '../api/types'
import { ALIAS_KINDS, FINGERPRINT_KINDS, SOURCES } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { canManageVips, formatDateTime } from '../lib/format'

function errorMessage(caught: unknown, fallback: string): string {
  return caught instanceof ApiError ? caught.detail : fallback
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-lg bg-white p-4 shadow-sm">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h2>
      {children}
    </section>
  )
}

function Row({ children }: { children: ReactNode }) {
  return (
    <li className="flex items-center justify-between gap-2 rounded border border-slate-200 px-3 py-2 text-sm">
      {children}
    </li>
  )
}

function DeleteButton({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="shrink-0 rounded border border-red-200 px-2 py-0.5 text-xs text-red-600 hover:bg-red-50"
    >
      {label}
    </button>
  )
}

function VipSettings({ vip, canManage }: { vip: Vip; canManage: boolean }) {
  const queryClient = useQueryClient()
  const [name, setName] = useState(vip.name)
  const [sensitivity, setSensitivity] = useState<Sensitivity>(vip.sensitivity)
  const [monitoring, setMonitoring] = useState(vip.monitoring_active)
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () =>
      updateVip(vip.id, {
        name: name.trim() || undefined,
        sensitivity,
        monitoring_active: monitoring,
      }),
    onSuccess: async () => {
      setError(null)
      await queryClient.invalidateQueries({ queryKey: ['vip', vip.id] })
      await queryClient.invalidateQueries({ queryKey: ['vips'] })
    },
    onError: (caught) => setError(errorMessage(caught, 'Could not update the VIP')),
  })

  return (
    <Panel title="Settings">
      <div className="space-y-3">
        <div>
          <label className="block text-sm font-medium" htmlFor="settings-name">
            Name
          </label>
          <input
            id="settings-name"
            value={name}
            disabled={!canManage}
            onChange={(event) => setName(event.target.value)}
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2 disabled:bg-slate-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium" htmlFor="settings-sensitivity">
            Sensitivity
          </label>
          <select
            id="settings-sensitivity"
            value={sensitivity}
            disabled={!canManage}
            onChange={(event) => setSensitivity(event.target.value as Sensitivity)}
            className="mt-1 w-full rounded border border-slate-300 bg-white px-3 py-2 disabled:bg-slate-100"
          >
            <option value="low">low</option>
            <option value="normal">normal</option>
            <option value="high">high</option>
          </select>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={monitoring}
            disabled={!canManage}
            onChange={(event) => setMonitoring(event.target.checked)}
            className="h-4 w-4"
          />
          Monitoring active
        </label>
        {canManage ? (
          <button
            type="button"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate()}
            className="rounded bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            Save
          </button>
        ) : null}
        {error ? (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        ) : null}
      </div>
    </Panel>
  )
}

function AliasSection({ vipId, canManage }: { vipId: string; canManage: boolean }) {
  const queryClient = useQueryClient()
  const [alias, setAlias] = useState('')
  const [kind, setKind] = useState<AliasKind>('name')
  const [ambiguous, setAmbiguous] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const query = useQuery({ queryKey: ['vip', vipId, 'aliases'], queryFn: () => fetchAliases(vipId) })
  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['vip', vipId, 'aliases'] })
  }

  const createMutation = useMutation({
    mutationFn: () => createAlias(vipId, { alias: alias.trim(), kind, is_ambiguous: ambiguous }),
    onSuccess: async () => {
      setAlias('')
      setAmbiguous(false)
      setError(null)
      await invalidate()
    },
    onError: (caught) => setError(errorMessage(caught, 'Could not add the alias')),
  })
  const deleteMutation = useMutation({
    mutationFn: ({ aliasValue, aliasKind }: { aliasValue: string; aliasKind: AliasKind }) =>
      deleteAlias(vipId, aliasKind, aliasValue),
    onSuccess: invalidate,
    onError: (caught) => setError(errorMessage(caught, 'Could not delete the alias')),
  })

  return (
    <Panel title="Aliases">
      <ul className="space-y-2">
        {(query.data ?? []).length === 0 ? <li className="text-sm text-slate-500">No aliases.</li> : null}
        {(query.data ?? []).map((row) => (
          <Row key={`${row.kind}:${row.alias}`}>
            <span>
              {row.alias}
              <span className="ml-2 text-xs text-slate-500">
                {row.kind}
                {row.is_ambiguous ? ' · ambiguous' : ''}
              </span>
            </span>
            {canManage ? (
              <DeleteButton
                label="Remove"
                onClick={() => deleteMutation.mutate({ aliasValue: row.alias, aliasKind: row.kind })}
              />
            ) : null}
          </Row>
        ))}
      </ul>
      {canManage ? (
        <form
          className="mt-3 flex flex-wrap items-end gap-2"
          onSubmit={(event: FormEvent) => {
            event.preventDefault()
            if (alias.trim()) {
              createMutation.mutate()
            }
          }}
        >
          <input
            aria-label="Alias"
            value={alias}
            onChange={(event) => setAlias(event.target.value)}
            placeholder="Alias"
            className="rounded border border-slate-300 px-2 py-1.5 text-sm"
          />
          <select
            aria-label="Alias kind"
            value={kind}
            onChange={(event) => setKind(event.target.value as AliasKind)}
            className="rounded border border-slate-300 bg-white px-2 py-1.5 text-sm"
          >
            {ALIAS_KINDS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-1 text-xs text-slate-600">
            <input
              type="checkbox"
              checked={ambiguous}
              onChange={(event) => setAmbiguous(event.target.checked)}
              className="h-4 w-4"
            />
            ambiguous
          </label>
          <button
            type="submit"
            disabled={createMutation.isPending || alias.trim().length === 0}
            className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          >
            Add
          </button>
        </form>
      ) : null}
      {error ? (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {error}
        </p>
      ) : null}
    </Panel>
  )
}

function KeywordSection({ vipId, canManage }: { vipId: string; canManage: boolean }) {
  const queryClient = useQueryClient()
  const [keyword, setKeyword] = useState('')
  const [error, setError] = useState<string | null>(null)

  const query = useQuery({
    queryKey: ['vip', vipId, 'keywords'],
    queryFn: () => fetchContextKeywords(vipId),
  })
  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['vip', vipId, 'keywords'] })
  }
  const createMutation = useMutation({
    mutationFn: () => createContextKeyword(vipId, keyword.trim()),
    onSuccess: async () => {
      setKeyword('')
      setError(null)
      await invalidate()
    },
    onError: (caught) => setError(errorMessage(caught, 'Could not add the keyword')),
  })
  const deleteMutation = useMutation({
    mutationFn: (value: string) => deleteContextKeyword(vipId, value),
    onSuccess: invalidate,
    onError: (caught) => setError(errorMessage(caught, 'Could not delete the keyword')),
  })

  return (
    <Panel title="Context keywords">
      <ul className="space-y-2">
        {(query.data ?? []).length === 0 ? (
          <li className="text-sm text-slate-500">No context keywords.</li>
        ) : null}
        {(query.data ?? []).map((row) => (
          <Row key={row.keyword}>
            <span>{row.keyword}</span>
            {canManage ? (
              <DeleteButton label="Remove" onClick={() => deleteMutation.mutate(row.keyword)} />
            ) : null}
          </Row>
        ))}
      </ul>
      {canManage ? (
        <form
          className="mt-3 flex gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            if (keyword.trim()) {
              createMutation.mutate()
            }
          }}
        >
          <input
            aria-label="Context keyword"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            className="rounded border border-slate-300 px-2 py-1.5 text-sm"
          />
          <button
            type="submit"
            disabled={createMutation.isPending || keyword.trim().length === 0}
            className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          >
            Add
          </button>
        </form>
      ) : null}
      {error ? (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {error}
        </p>
      ) : null}
    </Panel>
  )
}

function OfficialAccountSection({ vipId, canManage }: { vipId: string; canManage: boolean }) {
  const queryClient = useQueryClient()
  const [source, setSource] = useState<Source>('telegram')
  const [platformId, setPlatformId] = useState('')
  const [handle, setHandle] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [evidence, setEvidence] = useState('')
  const [error, setError] = useState<string | null>(null)

  const query = useQuery({
    queryKey: ['vip', vipId, 'official-accounts'],
    queryFn: () => fetchOfficialAccounts(vipId),
  })
  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['vip', vipId, 'official-accounts'] })
  }
  const createMutation = useMutation({
    mutationFn: () =>
      createOfficialAccount(vipId, {
        source,
        platform_account_id: platformId.trim(),
        handle: handle.trim() || undefined,
        display_name: displayName.trim() || undefined,
        verification_evidence: evidence.trim() || undefined,
      }),
    onSuccess: async () => {
      setPlatformId('')
      setHandle('')
      setDisplayName('')
      setEvidence('')
      setError(null)
      await invalidate()
    },
    onError: (caught) => setError(errorMessage(caught, 'Could not add the official account')),
  })
  const deleteMutation = useMutation({
    mutationFn: (accountId: string) => deleteOfficialAccount(vipId, accountId),
    onSuccess: invalidate,
    onError: (caught) => setError(errorMessage(caught, 'Could not delete the official account')),
  })

  return (
    <Panel title="Official accounts">
      <ul className="space-y-2">
        {(query.data ?? []).length === 0 ? (
          <li className="text-sm text-slate-500">No official accounts.</li>
        ) : null}
        {(query.data ?? []).map((row) => (
          <Row key={row.id}>
            <span>
              {row.display_name ?? row.handle ?? row.platform_account_id}
              <span className="ml-2 text-xs text-slate-500">
                {row.source} · {row.platform_account_id}
                {row.verified_at ? ' · verified' : ' · unverified'}
              </span>
            </span>
            {canManage ? (
              <DeleteButton label="Remove" onClick={() => deleteMutation.mutate(row.id)} />
            ) : null}
          </Row>
        ))}
      </ul>
      {canManage ? (
        <form
          className="mt-3 grid gap-2 md:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault()
            if (platformId.trim()) {
              createMutation.mutate()
            }
          }}
        >
          <select
            aria-label="Source"
            value={source}
            onChange={(event) => setSource(event.target.value as Source)}
            className="rounded border border-slate-300 bg-white px-2 py-1.5 text-sm"
          >
            {SOURCES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
          <input
            aria-label="Platform account id"
            value={platformId}
            onChange={(event) => setPlatformId(event.target.value)}
            placeholder="Platform account id"
            className="rounded border border-slate-300 px-2 py-1.5 text-sm"
          />
          <input
            aria-label="Handle"
            value={handle}
            onChange={(event) => setHandle(event.target.value)}
            placeholder="Handle"
            className="rounded border border-slate-300 px-2 py-1.5 text-sm"
          />
          <input
            aria-label="Display name"
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            placeholder="Display name"
            className="rounded border border-slate-300 px-2 py-1.5 text-sm"
          />
          <input
            aria-label="Verification evidence"
            value={evidence}
            onChange={(event) => setEvidence(event.target.value)}
            placeholder="Verification evidence"
            className="rounded border border-slate-300 px-2 py-1.5 text-sm md:col-span-2"
          />
          <button
            type="submit"
            disabled={createMutation.isPending || platformId.trim().length === 0}
            className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white disabled:opacity-50 md:col-span-2"
          >
            Add official account
          </button>
        </form>
      ) : null}
      {error ? (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {error}
        </p>
      ) : null}
    </Panel>
  )
}

function ReferenceMediaSection({ vipId, canManage }: { vipId: string; canManage: boolean }) {
  const queryClient = useQueryClient()
  const [kind, setKind] = useState<ReferenceMediaKind>('portrait')
  const [error, setError] = useState<string | null>(null)

  const query = useQuery({
    queryKey: ['vip', vipId, 'reference-media'],
    queryFn: () => fetchReferenceMedia(vipId),
  })
  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['vip', vipId, 'reference-media'] })
  }
  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadReferenceMedia(vipId, file, kind),
    onSuccess: async () => {
      setError(null)
      await invalidate()
    },
    onError: (caught) => setError(errorMessage(caught, 'Could not upload the reference image')),
  })
  const deleteMutation = useMutation({
    mutationFn: (mediaId: string) => deleteReferenceMedia(vipId, mediaId),
    onSuccess: invalidate,
    onError: (caught) => setError(errorMessage(caught, 'Could not delete the reference image')),
  })

  return (
    <Panel title="Reference media">
      <ul className="space-y-2">
        {(query.data ?? []).length === 0 ? (
          <li className="text-sm text-slate-500">No reference images.</li>
        ) : null}
        {(query.data ?? []).map((row) => (
          <Row key={row.id}>
            <span className="min-w-0">
              <span className="block truncate text-xs text-slate-600">{row.object_key}</span>
              <span className="text-xs text-slate-400">
                {row.kind} · {formatDateTime(row.created_at)}
              </span>
            </span>
            {canManage ? (
              <DeleteButton label="Remove" onClick={() => deleteMutation.mutate(row.id)} />
            ) : null}
          </Row>
        ))}
      </ul>
      {canManage ? (
        <form
          className="mt-3 flex flex-wrap items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            const file = (event.currentTarget.elements.namedItem('reference-file') as HTMLInputElement).files?.[0]
            if (file) {
              uploadMutation.mutate(file)
            }
          }}
        >
          <select
            aria-label="Reference kind"
            value={kind}
            onChange={(event) => setKind(event.target.value as ReferenceMediaKind)}
            className="rounded border border-slate-300 bg-white px-2 py-1.5 text-sm"
          >
            <option value="portrait">portrait</option>
            <option value="avatar">avatar</option>
            <option value="official_media">official_media</option>
          </select>
          <input
            name="reference-file"
            aria-label="Reference file"
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="text-sm"
          />
          <button
            type="submit"
            disabled={uploadMutation.isPending}
            className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          >
            Upload
          </button>
        </form>
      ) : null}
      {error ? (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {error}
        </p>
      ) : null}
    </Panel>
  )
}

function FingerprintSection({ vipId, canManage }: { vipId: string; canManage: boolean }) {
  const queryClient = useQueryClient()
  const [kind, setKind] = useState<FingerprintKind>('phone')
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)

  const query = useQuery({
    queryKey: ['vip', vipId, 'fingerprints'],
    queryFn: () => fetchFingerprints(vipId),
  })
  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['vip', vipId, 'fingerprints'] })
  }
  const createMutation = useMutation({
    mutationFn: () => createFingerprint(vipId, { kind, value: value.trim() }),
    onSuccess: async () => {
      setValue('')
      setError(null)
      await invalidate()
    },
    onError: (caught) => setError(errorMessage(caught, 'Could not register the value')),
  })
  const deleteMutation = useMutation({
    mutationFn: (fingerprintId: string) => deleteFingerprint(vipId, fingerprintId),
    onSuccess: invalidate,
    onError: (caught) => setError(errorMessage(caught, 'Could not delete the fingerprint')),
  })

  return (
    <Panel title="Sensitive fingerprints">
      <ul className="space-y-2">
        {(query.data ?? []).length === 0 ? (
          <li className="text-sm text-slate-500">No registered values.</li>
        ) : null}
        {(query.data ?? []).map((row) => (
          <Row key={row.id}>
            <span>
              {row.kind}
              <span className="ml-2 text-xs text-slate-500">
                salt {row.salt_id} · {formatDateTime(row.created_at)}
              </span>
            </span>
            {canManage ? (
              <DeleteButton label="Remove" onClick={() => deleteMutation.mutate(row.id)} />
            ) : null}
          </Row>
        ))}
      </ul>
      {canManage ? (
        <form
          className="mt-3 flex flex-wrap items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            if (value.trim()) {
              createMutation.mutate()
            }
          }}
        >
          <select
            aria-label="Fingerprint kind"
            value={kind}
            onChange={(event) => setKind(event.target.value as FingerprintKind)}
            className="rounded border border-slate-300 bg-white px-2 py-1.5 text-sm"
          >
            {FINGERPRINT_KINDS.map((entry) => (
              <option key={entry} value={entry}>
                {entry}
              </option>
            ))}
          </select>
          <input
            aria-label="Fingerprint value"
            type="password"
            autoComplete="off"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder="Value"
            className="rounded border border-slate-300 px-2 py-1.5 text-sm"
          />
          <button
            type="submit"
            disabled={createMutation.isPending || value.trim().length === 0}
            className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          >
            Register
          </button>
          <p className="w-full text-xs text-slate-400">
            Values are salted-hashed on the server and the plaintext is discarded.
          </p>
        </form>
      ) : null}
      {error ? (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {error}
        </p>
      ) : null}
    </Panel>
  )
}

export function VipDetailPage() {
  const { vipId = '' } = useParams()
  const { role } = useAuth()
  const canManage = canManageVips(role)

  const vipQuery = useQuery({
    queryKey: ['vip', vipId],
    queryFn: () => fetchVip(vipId),
    enabled: Boolean(vipId),
  })

  if (vipQuery.isLoading) {
    return <p className="text-sm text-slate-500">Loading VIP…</p>
  }
  if (vipQuery.isError || !vipQuery.data) {
    return (
      <div className="rounded-lg bg-white p-6 shadow-sm">
        <p className="text-sm text-slate-600">This VIP does not exist or is outside your scope.</p>
        <Link className="mt-3 inline-block text-sm" to="/vips">
          Back to VIPs
        </Link>
      </div>
    )
  }

  const vip = vipQuery.data

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <Link to="/vips" className="text-sm">
          ← Back to VIPs
        </Link>
        <h1 className="text-xl font-semibold">{vip.name}</h1>
        <span
          className={`rounded px-2 py-0.5 text-xs ${
            vip.monitoring_active ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-600'
          }`}
        >
          {vip.monitoring_active ? 'monitoring' : 'paused'}
        </span>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <VipSettings vip={vip} canManage={canManage} />
        <AliasSection vipId={vip.id} canManage={canManage} />
        <KeywordSection vipId={vip.id} canManage={canManage} />
        <OfficialAccountSection vipId={vip.id} canManage={canManage} />
        <ReferenceMediaSection vipId={vip.id} canManage={canManage} />
        <FingerprintSection vipId={vip.id} canManage={canManage} />
      </div>
    </div>
  )
}
