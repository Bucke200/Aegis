import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'

import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'

export function LoginPage() {
  const { login, status } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from ?? '/incidents'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [mfaRequired, setMfaRequired] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (status === 'authenticated') {
    return <Navigate to={from} replace />
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email, password, mfaRequired ? totpCode : undefined)
      navigate(from, { replace: true })
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401 && caught.detail === 'invalid MFA code') {
        setMfaRequired(true)
        setError('Enter the 6-digit code from your authenticator app.')
      } else if (caught instanceof ApiError && caught.status === 401) {
        setError('Invalid email or password.')
      } else if (caught instanceof ApiError && caught.status === 429) {
        setError('Too many attempts. Wait a moment and try again.')
      } else {
        setError(caught instanceof Error ? caught.message : 'Sign in failed.')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 p-4">
      <form onSubmit={(event) => void submit(event)} className="w-full max-w-sm rounded-lg bg-white p-8 shadow">
        <h1 className="text-2xl font-bold tracking-tight">Aegis</h1>
        <p className="mt-1 text-sm text-slate-500">Threat monitoring console</p>

        <label className="mt-6 block text-sm font-medium" htmlFor="email">
          Email
        </label>
        <input
          id="email"
          type="email"
          required
          autoComplete="username"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
        />

        <label className="mt-4 block text-sm font-medium" htmlFor="password">
          Password
        </label>
        <input
          id="password"
          type="password"
          required
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
        />

        {mfaRequired ? (
          <>
            <label className="mt-4 block text-sm font-medium" htmlFor="totp">
              Authenticator code
            </label>
            <input
              id="totp"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={totpCode}
              onChange={(event) => setTotpCode(event.target.value)}
              className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
              placeholder="123456"
            />
          </>
        ) : null}

        {error ? (
          <p role="alert" className="mt-4 text-sm text-red-600">
            {error}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={busy}
          className="mt-6 w-full rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-50"
        >
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
