"""
Shared data models for Aegis platform
"""
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from uuid import UUID, uuid4


class ThreatType(str, Enum):
    """Types of threats detected by the system"""
    IMPERSONATION = "impersonation"
    MISINFORMATION = "misinformation"
    THREAT = "threat"
    LEAK = "leak"
    COORDINATED_CAMPAIGN = "coordinated_campaign"


class Severity(str, Enum):
    """Severity levels for incidents"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, Enum):
    """Status of incident investigation"""
    NEW = "new"
    REVIEWING = "reviewing"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


class Platform(str, Enum):
    """Supported data sources and platforms for monitoring"""
    TWITTER = "twitter"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    LINKEDIN = "linkedin"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    PASTEBIN = "pastebin"
    GITHUB = "github"
    MANUAL = "manual"
    SYSTEM = "system"


class Evidence(BaseModel):
    """Evidence collected for an incident"""
    screenshot_url: Optional[str] = None
    media_urls: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    source_html: Optional[str] = None
    captured_at: datetime = Field(default_factory=datetime.utcnow)


class AnalysisResult(BaseModel):
    """Results from analysis modules"""
    module_name: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    details: Dict[str, Any] = Field(default_factory=dict)
    processed_at: datetime = Field(default_factory=datetime.utcnow)


class Incident(BaseModel):
    """Core incident model"""
    id: UUID = Field(default_factory=uuid4)
    vip_id: UUID
    platform: Platform
    severity: Severity
    threat_type: ThreatType
    content: str
    source_url: str
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    status: IncidentStatus = IncidentStatus.NEW
    evidence: Evidence = Field(default_factory=Evidence)
    analysis_results: List[AnalysisResult] = Field(default_factory=list)
    assigned_to: Optional[UUID] = None
    notes: str = ""
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class VIPProfile(BaseModel):
    """VIP profile configuration"""
    id: UUID = Field(default_factory=uuid4)
    name: str
    official_profiles: Dict[Platform, str] = Field(default_factory=dict)
    keywords: List[str] = Field(default_factory=list)
    monitoring_active: bool = True
    alert_settings: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Campaign(BaseModel):
    """Coordinated campaign detection"""
    id: UUID = Field(default_factory=uuid4)
    vip_id: UUID
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    account_count: int
    similarity_score: float = Field(ge=0.0, le=1.0)
    network_graph: Dict[str, Any] = Field(default_factory=dict)
    incidents: List[UUID] = Field(default_factory=list)
    status: IncidentStatus = IncidentStatus.NEW


class CollectedData(BaseModel):
    """Standardized format for collected data"""
    source: Platform
    author: str
    content: str
    url: str
    timestamp: datetime
    media_urls: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    collected_at: datetime = Field(default_factory=datetime.utcnow)