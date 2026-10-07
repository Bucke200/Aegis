import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

import * as authApi from '../api/auth'
import { setUnauthorizedHandler } from '../api/client'
import type { UserRead, UserRole } from '../api/types'

interface AuthContextValue {
  status: 'loading' | 'authenticated' | 'anonymous'
  user: UserRead | null
  role: UserRole | null
  scopedVipIds: string[]
  canReveal: (vipId: string) => boolean
  login: (email: string, password: string, totpCode?: string) => Promise<void>
  logout: () => Promise<void>
  refreshMe: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthContextValue['status']>('loading')
  const [user, setUser] = useState<UserRead | null>(null)
  const [scopes, setScopes] = useState<Array<{ vip_id: string; can_reveal_sensitive: boolean }>>([])

  const loadMe = useCallback(async () => {
    const me = await authApi.fetchMe()
    setUser(me.user)
    setScopes(me.scopes)
    setStatus('authenticated')
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const me = await authApi.fetchMe()
        if (!cancelled) {
          setUser(me.user)
          setScopes(me.scopes)
          setStatus('authenticated')
        }
      } catch {
        if (!cancelled) {
          setUser(null)
          setScopes([])
          setStatus('anonymous')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null)
      setScopes([])
      setStatus('anonymous')
    })
    return () => {
      setUnauthorizedHandler(null)
    }
  }, [])

  const login = useCallback(
    async (email: string, password: string, totpCode?: string) => {
      await authApi.login(email, password, totpCode)
      await loadMe()
    },
    [loadMe],
  )

  const logout = useCallback(async () => {
    await authApi.logout()
    setUser(null)
    setScopes([])
    setStatus('anonymous')
  }, [])

  const refreshMe = useCallback(async () => {
    await loadMe()
  }, [loadMe])

  const canReveal = useCallback(
    (vipId: string) => scopes.some((scope) => scope.vip_id === vipId && scope.can_reveal_sensitive),
    [scopes],
  )

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      role: user?.role ?? null,
      scopedVipIds: scopes.map((scope) => scope.vip_id),
      canReveal,
      login,
      logout,
      refreshMe,
    }),
    [status, user, scopes, canReveal, login, logout, refreshMe],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider')
  }
  return context
}
