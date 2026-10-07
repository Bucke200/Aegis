export type Severity = 'low' | 'medium' | 'high' | 'critical'
export type IncidentStatus = 'new' | 'under_review' | 'escalated' | 'resolved' | 'false_positive'
export type IncidentSubject = 'item' | 'account'
export type IncidentOutcome =
  | 'reported_to_platform'
  | 'taken_down'
  | 'referred_to_authorities'
  | 'no_action_needed'
  | 'below_threshold'
export type IncidentEventType =
  | 'status_change'
  | 'assign'
  | 'note'
  | 'severity_override'
  | 'rescore'
  | 'item_attached'
  | 'merged_into'
  | 'campaign_linked'
export type UserRole = 'admin' | 'lead' | 'analyst' | 'viewer'
export type Source =
  | 'replay'
  | 'manual'
  | 'telegram'
  | 'github'
  | 'x'
  | 'facebook'
  | 'instagram'
  | 'youtube'
  | 'discord'
  | 'pastebin'
export type Sensitivity = 'low' | 'normal' | 'high'
export type AliasKind = 'name' | 'nickname' | 'transliteration' | 'handle' | 'hashtag'
export type ReferenceMediaKind = 'portrait' | 'avatar' | 'official_media'
export type FingerprintKind = 'phone' | 'email' | 'address_token' | 'other'
export type InputVariant = 'text' | 'ocr_text' | 'media'

export const SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low']
export const INCIDENT_STATUSES: IncidentStatus[] = [
  'new',
  'under_review',
  'escalated',
  'resolved',
  'false_positive',
]
export const THREAT_TYPES = [
  'violent_threat',
  'harassment',
  'incitement',
  'doxxing',
  'impersonation',
  'solicitation',
  'leak',
  'repurposed_media',
  'campaign',
] as const
export const SOURCES: Source[] = [
  'replay',
  'manual',
  'telegram',
  'github',
  'x',
  'facebook',
  'instagram',
  'youtube',
  'discord',
  'pastebin',
]
export const LANGUAGES = ['en', 'hi', 'hi-Latn']
export const ALIAS_KINDS: AliasKind[] = ['name', 'nickname', 'transliteration', 'handle', 'hashtag']
export const FINGERPRINT_KINDS: FingerprintKind[] = ['phone', 'email', 'address_token', 'other']

export interface TokenResponse {
  access_token: string
  token_type: string
  role: UserRole
}

export interface UserSummary {
  id: string
  email: string
  display_name: string | null
  role: UserRole
}

export interface UserRead extends UserSummary {
  mfa_enabled: boolean
  is_active: boolean
  created_at: string
}

export interface UserScope {
  user_id: string
  vip_id: string
  can_reveal_sensitive: boolean
}

export interface MeResponse {
  user: UserRead
  scopes: UserScope[]
}

export interface MfaEnrollResponse {
  secret: string
  otpauth_url: string
}

export interface MfaVerifyResponse {
  enabled: boolean
}

export interface AccountSummary {
  id: string
  source: Source
  platform_account_id: string
  handle: string | null
  display_name: string | null
}

export interface ItemSummary {
  id: string
  source: Source
  platform_item_id: string
  url: string | null
  text: string | null
  language: string | null
  collected_at: string
}

export interface Incident {
  id: string
  subject_type: IncidentSubject
  item_id: string | null
  account_id: string | null
  source: Source
  language: string | null
  risk_score: number
  severity: Severity
  threat_types: string[]
  explanation: string | null
  status: IncidentStatus
  assignee_id: string | null
  campaign_id: string | null
  outcome: IncidentOutcome | null
  below_threshold: boolean
  merged_into_id: string | null
  created_at: string
  updated_at: string
  vip_ids: string[]
  item: ItemSummary | null
  assignee: UserSummary | null
  account: AccountSummary | null
}

export interface Detection {
  id: string
  detector: string
  model_version: string
  input_variant: InputVariant
  score: number
  label: string | null
  spans: DetectionSpan[]
  details: Record<string, unknown>
  created_at: string
}

export interface DetectionSpan {
  start?: number
  end?: number
  text?: string
  category?: string
  [key: string]: unknown
}

export interface IncidentEvent {
  id: string
  event_type: IncidentEventType
  actor_id: string | null
  from_value: Record<string, unknown> | null
  to_value: Record<string, unknown> | null
  reason: string | null
  at: string
}

export interface IncidentNote {
  id: string
  author_id: string | null
  body: string
  created_at: string
}

export interface EvidenceArtifact {
  id: string
  kind: string
  object_key: string
  sha256: string
  size: number
  captured_at: string
}

export interface CampaignSummary {
  id: string
  status: string
  coordination_score: number | null
  account_count: number
  item_count: number
}

export interface IncidentDetail {
  incident: Incident
  detections: Detection[]
  account: AccountSummary | null
  campaign: CampaignSummary | null
  history: IncidentEvent[]
  notes: IncidentNote[]
  evidence: EvidenceArtifact[]
}

export interface IncidentListResponse {
  items: Incident[]
  next_cursor: string | null
}

export interface Vip {
  id: string
  name: string
  sensitivity: Sensitivity
  monitoring_active: boolean
  config_version: number
  created_at: string
}

export interface Alias {
  vip_id: string
  alias: string
  kind: AliasKind
  is_ambiguous: boolean
}

export interface ContextKeyword {
  vip_id: string
  keyword: string
}

export interface OfficialAccount {
  id: string
  vip_id: string
  source: Source
  platform_account_id: string
  handle: string | null
  display_name: string | null
  bio: string | null
  verification_evidence: string | null
  profile_refreshed_at: string | null
  verified_at: string | null
}

export interface ReferenceMedia {
  id: string
  vip_id: string
  object_key: string
  kind: ReferenceMediaKind
  phash: string | null
  dhash: string | null
  created_at: string
}

export interface Fingerprint {
  id: string
  vip_id: string
  kind: FingerprintKind
  salt_id: string
  created_at: string
}

export interface SocketEvent {
  type: 'ready' | 'created' | 'updated' | 'merged'
  incident_id?: string
  severity?: Severity
  risk_score?: number
  vip_ids?: string[]
  merged_into_id?: string
}
