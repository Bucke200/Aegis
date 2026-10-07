import { apiFetch } from './client'
import type {
  Alias,
  AliasKind,
  ContextKeyword,
  Fingerprint,
  FingerprintKind,
  OfficialAccount,
  ReferenceMedia,
  ReferenceMediaKind,
  Sensitivity,
  Source,
  Vip,
} from './types'

export async function fetchVips(): Promise<Vip[]> {
  return apiFetch<Vip[]>('/vips')
}

export async function fetchVip(vipId: string): Promise<Vip> {
  return apiFetch<Vip>(`/vips/${vipId}`)
}

export async function createVip(input: {
  name: string
  sensitivity: Sensitivity
  monitoring_active: boolean
}): Promise<Vip> {
  return apiFetch<Vip>('/vips', { method: 'POST', body: input })
}

export async function updateVip(
  vipId: string,
  input: { name?: string; sensitivity?: Sensitivity; monitoring_active?: boolean },
): Promise<Vip> {
  return apiFetch<Vip>(`/vips/${vipId}`, { method: 'PATCH', body: input })
}

export async function fetchAliases(vipId: string): Promise<Alias[]> {
  return apiFetch<Alias[]>(`/vips/${vipId}/aliases`)
}

export async function createAlias(
  vipId: string,
  input: { alias: string; kind: AliasKind; is_ambiguous: boolean },
): Promise<Alias> {
  return apiFetch<Alias>(`/vips/${vipId}/aliases`, { method: 'POST', body: input })
}

export async function deleteAlias(vipId: string, kind: AliasKind, alias: string): Promise<void> {
  return apiFetch(`/vips/${vipId}/aliases/${kind}/${encodeURIComponent(alias)}`, { method: 'DELETE' })
}

export async function fetchContextKeywords(vipId: string): Promise<ContextKeyword[]> {
  return apiFetch<ContextKeyword[]>(`/vips/${vipId}/context-keywords`)
}

export async function createContextKeyword(vipId: string, keyword: string): Promise<ContextKeyword> {
  return apiFetch<ContextKeyword>(`/vips/${vipId}/context-keywords`, { method: 'POST', body: { keyword } })
}

export async function deleteContextKeyword(vipId: string, keyword: string): Promise<void> {
  return apiFetch(`/vips/${vipId}/context-keywords/${encodeURIComponent(keyword)}`, { method: 'DELETE' })
}

export async function fetchOfficialAccounts(vipId: string): Promise<OfficialAccount[]> {
  return apiFetch<OfficialAccount[]>(`/vips/${vipId}/official-accounts`)
}

export async function createOfficialAccount(
  vipId: string,
  input: {
    source: Source
    platform_account_id: string
    handle?: string
    display_name?: string
    bio?: string
    verification_evidence?: string
  },
): Promise<OfficialAccount> {
  return apiFetch<OfficialAccount>(`/vips/${vipId}/official-accounts`, { method: 'POST', body: input })
}

export async function deleteOfficialAccount(vipId: string, accountId: string): Promise<void> {
  return apiFetch(`/vips/${vipId}/official-accounts/${accountId}`, { method: 'DELETE' })
}

export async function fetchReferenceMedia(vipId: string): Promise<ReferenceMedia[]> {
  return apiFetch<ReferenceMedia[]>(`/vips/${vipId}/reference-media`)
}

export async function uploadReferenceMedia(
  vipId: string,
  file: File,
  kind: ReferenceMediaKind,
): Promise<ReferenceMedia> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('kind', kind)
  return apiFetch<ReferenceMedia>(`/vips/${vipId}/reference-media`, { method: 'POST', formData })
}

export async function deleteReferenceMedia(vipId: string, mediaId: string): Promise<void> {
  return apiFetch(`/vips/${vipId}/reference-media/${mediaId}`, { method: 'DELETE' })
}

export async function fetchFingerprints(vipId: string): Promise<Fingerprint[]> {
  return apiFetch<Fingerprint[]>(`/vips/${vipId}/sensitive-fingerprints`)
}

export async function createFingerprint(
  vipId: string,
  input: { kind: FingerprintKind; value: string },
): Promise<Fingerprint> {
  return apiFetch<Fingerprint>(`/vips/${vipId}/sensitive-fingerprints`, { method: 'POST', body: input })
}

export async function deleteFingerprint(vipId: string, fingerprintId: string): Promise<void> {
  return apiFetch(`/vips/${vipId}/sensitive-fingerprints/${fingerprintId}`, { method: 'DELETE' })
}
