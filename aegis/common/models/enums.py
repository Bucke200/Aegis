"""Domain enumerations stored as validated strings."""

from __future__ import annotations

from enum import StrEnum


class Sensitivity(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class AliasKind(StrEnum):
    NAME = "name"
    NICKNAME = "nickname"
    TRANSLITERATION = "transliteration"
    HANDLE = "handle"
    HASHTAG = "hashtag"


class Source(StrEnum):
    REPLAY = "replay"
    MANUAL = "manual"
    TELEGRAM = "telegram"
    GITHUB = "github"
    X = "x"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"
    DISCORD = "discord"
    PASTEBIN = "pastebin"


class ReferenceMediaKind(StrEnum):
    PORTRAIT = "portrait"
    AVATAR = "avatar"
    OFFICIAL_MEDIA = "official_media"


class FingerprintKind(StrEnum):
    PHONE = "phone"
    EMAIL = "email"
    ADDRESS_TOKEN = "address_token"
    OTHER = "other"


class DiscoveredVia(StrEnum):
    AUTHORED_ITEM = "authored_item"
    MENTION = "mention"
    MANUAL_PROFILE = "manual_profile"
    PROFILE_SEARCH = "profile_search"


class ItemType(StrEnum):
    POST = "post"
    COMMENT = "comment"
    REPLY = "reply"
    MESSAGE = "message"
    PASTE = "paste"
    CODE_FILE = "code_file"


class MediaType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    FILE = "file"


class MatchSource(StrEnum):
    ALIAS = "alias"
    HANDLE = "handle"
    HASHTAG = "hashtag"
    MEDIA = "media"


class ScoreState(StrEnum):
    SCREENED_OUT = "screened_out"
    PENDING_EMBEDDINGS = "pending_embeddings"
    SCORED = "scored"
    PARTIAL = "partial"
    STALE = "stale"


class ItemChangeType(StrEnum):
    EDIT = "edit"
    DELETE = "delete"


class DetectionScope(StrEnum):
    ITEM = "item"
    ACCOUNT = "account"


class InputVariant(StrEnum):
    TEXT = "text"
    OCR_TEXT = "ocr_text"
    MEDIA = "media"


class IncidentSubject(StrEnum):
    ITEM = "item"
    ACCOUNT = "account"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(StrEnum):
    NEW = "new"
    UNDER_REVIEW = "under_review"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


class IncidentOutcome(StrEnum):
    REPORTED_TO_PLATFORM = "reported_to_platform"
    TAKEN_DOWN = "taken_down"
    REFERRED_TO_AUTHORITIES = "referred_to_authorities"
    NO_ACTION_NEEDED = "no_action_needed"
    BELOW_THRESHOLD = "below_threshold"


class IncidentEventType(StrEnum):
    STATUS_CHANGE = "status_change"
    ASSIGN = "assign"
    NOTE = "note"
    SEVERITY_OVERRIDE = "severity_override"
    RESCORE = "rescore"
    ITEM_ATTACHED = "item_attached"
    MERGED_INTO = "merged_into"
    CAMPAIGN_LINKED = "campaign_linked"


class CampaignStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class CampaignMemberType(StrEnum):
    ACCOUNT = "account"
    ITEM = "item"


class EdgeType(StrEnum):
    REPLY = "reply"
    REPOST = "repost"
    MENTION = "mention"
    CO_CLUSTER = "co_cluster"


class EvidenceKind(StrEnum):
    RAW = "raw"
    SCREENSHOT = "screenshot"
    HTML = "html"
    MEDIA = "media"
    ACCOUNT_SNAPSHOT = "account_snapshot"


class CustodyTargetType(StrEnum):
    ARTIFACT = "artifact"
    MANIFEST = "manifest"


class CustodyAction(StrEnum):
    VIEW = "view"
    DOWNLOAD = "download"
    EXPORT = "export"


class AlertScope(StrEnum):
    VIP = "vip"
    USER = "user"


class AlertChannel(StrEnum):
    EMAIL = "email"
    SLACK = "slack"
    SMS = "sms"


class AlertDeliveryStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    ACKNOWLEDGED = "acknowledged"


class LabelKind(StrEnum):
    FALSE_POSITIVE = "fp"
    TRUE_POSITIVE = "tp"
    CORRECTED_TYPE = "corrected_type"
    CORRECTED_SEVERITY = "corrected_severity"


class SuppressionScope(StrEnum):
    VIP = "vip"
    ACCOUNT = "account"
    KEYWORD = "keyword"
    DOMAIN = "domain"
    GLOBAL = "global"


class SourceHealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    AUTH_FAILED = "auth_failed"
    STALE = "stale"


class UserRole(StrEnum):
    ADMIN = "admin"
    LEAD = "lead"
    ANALYST = "analyst"
    VIEWER = "viewer"
