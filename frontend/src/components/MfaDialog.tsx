import { useState } from 'react'

import { enrollMfa, verifyMfa } from '../api/auth'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'

export function MfaDialog() {
  const { user, refreshMe } = useAuth()
  const [open, setOpen] = useState(false)
  const [secret, setSecret] = useState<string | null>(null)
  const [otpauthUrl, setOtpauthUrl] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (!user) {
    return null
  }

  const start = async () => {
    setBusy(true)
    setError(null)
    try {
      const response = await enrollMfa()
      setSecret(response.secret)
      setOtpauthUrl(response.otpauth_url)
      setOpen(true)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail : 'Could not start MFA enrolment')
    } finally {
      setBusy(false)
    }
  }

  const confirm = async () => {
    setBusy(true)
    setError(null)
    try {
      await verifyMfa(code.trim())
      await refreshMe()
      setOpen(false)
      setCode('')
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail : 'Could not verify the code')
    } finally {
      setBusy(false)
    }
  }

  if (user.mfa_enabled) {
    return <span className="text-xs text-slate-400">MFA enabled</span>
  }

  return (
    <>
      <button
        type="button"
        onClick={() => void start()}
        disabled={busy}
        className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 disabled:opacity-50"
      >
        Enable MFA
      </button>
      {open ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
            <h2 className="text-lg font-semibold">Enable MFA</h2>
            <p className="mt-2 text-sm text-slate-600">
              Add this secret to your authenticator app, then confirm with a generated code.
            </p>
            <p className="mt-3 break-all rounded bg-slate-100 p-3 font-mono text-sm">{secret}</p>
            {otpauthUrl ? (
              <a className="mt-2 block break-all text-xs" href={otpauthUrl}>
                {otpauthUrl}
              </a>
            ) : null}
            <input
              aria-label="Authenticator code"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              inputMode="numeric"
              className="mt-4 w-full rounded border border-slate-300 px-3 py-2"
              placeholder="123456"
            />
            {error ? <p className="mt-2 text-sm text-red-600">{error}</p> : null}
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                className="rounded border border-slate-300 px-3 py-1.5 text-sm"
                onClick={() => setOpen(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded bg-blue-700 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                disabled={busy || code.trim().length < 6}
                onClick={() => void confirm()}
              >
                Verify
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}
