import type { TokenResponse } from './types'

const configuredUrl = import.meta.env.VITE_API_URL as string | undefined
const API_URL = (configuredUrl ?? 'http://localhost:8000').replace(/\/$/, '')

export class ApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

let accessToken: string | null = null
let refreshPromise: Promise<string | null> | null = null
let unauthorizedHandler: (() => void) | null = null

export function apiBaseUrl(): string {
  return API_URL
}

export function websocketUrl(): string {
  return `${API_URL.replace(/^http/, 'ws')}/ws/incidents`
}

export function getAccessToken(): string | null {
  return accessToken
}

export function setAccessToken(token: string | null): void {
  accessToken = token
}

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler
}

async function parseDetail(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json()
    if (body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string') {
      return body.detail
    }
    return JSON.stringify(body)
  } catch {
    return response.statusText || 'request failed'
  }
}

async function requestRefresh(): Promise<string | null> {
  const response = await fetch(`${API_URL}/auth/refresh`, {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) {
    setAccessToken(null)
    return null
  }
  const body = (await response.json()) as TokenResponse
  setAccessToken(body.access_token)
  return body.access_token
}

function refreshOnce(): Promise<string | null> {
  refreshPromise ??= requestRefresh().finally(() => {
    refreshPromise = null
  })
  return refreshPromise
}

export async function ensureAccessToken(): Promise<string | null> {
  if (accessToken) {
    return accessToken
  }
  return refreshOnce()
}

export interface RequestOptions {
  method?: string
  body?: unknown
  formData?: FormData
  auth?: boolean
  retryOnUnauthorized?: boolean
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, formData, auth = true, retryOnUnauthorized = true } = options
  const headers: Record<string, string> = {}
  if (auth) {
    const token = await ensureAccessToken()
    if (token) {
      headers.Authorization = `Bearer ${token}`
    }
  }
  let payload: BodyInit | undefined
  if (formData) {
    payload = formData
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }

  const response = await fetch(`${API_URL}${path}`, {
    method,
    headers,
    body: payload,
    credentials: 'include',
  })

  if (response.status === 401 && auth && retryOnUnauthorized) {
    setAccessToken(null)
    const token = await refreshOnce()
    if (token) {
      return apiFetch<T>(path, { ...options, retryOnUnauthorized: false })
    }
    unauthorizedHandler?.()
    throw new ApiError(401, 'session expired')
  }
  if (!response.ok) {
    throw new ApiError(response.status, await parseDetail(response))
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}
