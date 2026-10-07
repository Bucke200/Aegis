import { NavLink, Outlet, useNavigate } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { useIncidentSocket } from '../hooks/useIncidentSocket'
import { ROLE_LABELS } from '../lib/format'
import { MfaDialog } from './MfaDialog'

function navClass({ isActive }: { isActive: boolean }): string {
  return `rounded px-3 py-1.5 text-sm font-medium ${
    isActive ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-200'
  }`
}

export function AppShell() {
  const { user, role, logout } = useAuth()
  const { connected } = useIncidentSocket(Boolean(user))
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-2 px-4 py-3">
          <span className="mr-2 text-lg font-bold tracking-tight">Aegis</span>
          <nav className="flex items-center gap-1">
            <NavLink to="/incidents" className={navClass}>
              Incidents
            </NavLink>
            <NavLink to="/vips" className={navClass}>
              VIPs
            </NavLink>
          </nav>
          <div className="ml-auto flex flex-wrap items-center gap-3">
            <span
              data-testid="connection-status"
              className="flex items-center gap-1.5 text-xs text-slate-500"
              title={connected ? 'Live updates connected' : 'Live updates reconnecting'}
            >
              <span className={`h-2 w-2 rounded-full ${connected ? 'bg-emerald-500' : 'bg-amber-500'}`} />
              {connected ? 'Live' : 'Reconnecting'}
            </span>
            <MfaDialog />
            <span className="text-sm text-slate-600">{user?.display_name ?? user?.email}</span>
            <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
              {role ? ROLE_LABELS[role] : ''}
            </span>
            <button
              type="button"
              className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-100"
              onClick={() => {
                void logout().then(() => navigate('/login'))
              }}
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
