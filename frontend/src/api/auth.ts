import { apiFetch, setAccessToken } from './client'
import type { MeResponse, MfaEnrollResponse, MfaVerifyResponse, TokenResponse } from './types'

export async function login(email: string, password: string, totpCode?: string): Promise<TokenResponse> {
  const body = {
    email,
    password,
    totp_code: totpCode?.trim() ? totpCode.trim() : null,
  }
  const response = await apiFetch<TokenResponse>('/auth/login', { method: 'POST', body, auth: false })
  setAccessToken(response.access_token)
  return response
}

export async function fetchMe(): Promise<MeResponse> {
  return apiFetch<MeResponse>('/auth/me')
}

export async function logout(): Promise<void> {
  try {
    await apiFetch('/auth/logout', { method: 'POST' })
  } finally {
    setAccessToken(null)
  }
}

export async function enrollMfa(): Promise<MfaEnrollResponse> {
  return apiFetch<MfaEnrollResponse>('/auth/mfa/enroll', { method: 'POST' })
}

export async function verifyMfa(code: string): Promise<MfaVerifyResponse> {
  return apiFetch<MfaVerifyResponse>('/auth/mfa/verify', { method: 'POST', body: { code } })
}
