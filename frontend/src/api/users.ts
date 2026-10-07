import { apiFetch } from './client'
import type { UserSummary } from './types'

export async function fetchDirectory(): Promise<UserSummary[]> {
  return apiFetch<UserSummary[]>('/users/directory')
}
