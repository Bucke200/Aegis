"""
Message schemas and validation for standardized data format
"""
import json
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, validator
from uuid import uuid4


class MessageType(str, Enum):
    """Standard message types"""
    SOCIAL_MEDIA = "social_media"
    WEB_SCRAPING = "web_scraping"
    MESSAGING_PLATFORM = "messaging_platform"
    THREAT_ANALYSIS = "threat_analysis"
    INCIDENT_ALERT = "incident_alert"
    EVIDENCE_REQUEST = "evidence_request"
    SYSTEM_EVENT = "system_event"


class Priority(str, Enum):
    """Message priority levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SourceType(str, Enum):
    """Data source types"""
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


class ContentType(str, Enum):
    """Content types"""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    URL = "url"
    PROFILE = "profile"


# Base message schema
class BaseMessage(BaseModel):
    """Base message structure for all message types"""
    
    message_id: str = Field(default_factory=lambda: str(uuid4()))
    message_type: MessageType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source: SourceType
    priority: Priority = Priority.MEDIUM
    
    # Routing information
    routing_key: Optional[str] = None
    exchange: Optional[str] = None
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# Social Media Message Schema
class SocialMediaContent(BaseModel):
    """Social media content structure"""
    
    post_id: str
    author_id: str
    author_username: str
    author_display_name: Optional[str] = None
    content: str
    content_type: ContentType = ContentType.TEXT
    
    # Post metadata
    created_at: datetime
    url: Optional[str] = None
    language: Optional[str] = None
    
    # Engagement metrics
    likes: Optional[int] = 0
    shares: Optional[int] = 0
    comments: Optional[int] = 0
    views: Optional[int] = 0
    
    # Media attachments
    media_urls: List[str] = Field(default_factory=list)
    
    # Author profile info
    author_followers: Optional[int] = None
    author_verified: Optional[bool] = None
    author_created_at: Optional[datetime] = None
    
    # Hashtags and mentions
    hashtags: List[str] = Field(default_factory=list)
    mentions: List[str] = Field(default_factory=list)
    
    # Geographic data
    location: Optional[str] = None
    coordinates: Optional[Dict[str, float]] = None


class SocialMediaMessage(BaseMessage):
    """Social media monitoring message"""
    
    message_type: MessageType = MessageType.SOCIAL_MEDIA
    data: SocialMediaContent
    
    # VIP monitoring context
    monitored_vip: Optional[str] = None
    monitoring_keywords: List[str] = Field(default_factory=list)
    
    @validator('routing_key', always=True)
    def set_routing_key(cls, v, values):
        if not v and 'source' in values:
            return f"social.{values['source']}"
        return v


# Web Scraping Message Schema
class WebScrapingContent(BaseModel):
    """Web scraping content structure"""
    
    url: str
    title: Optional[str] = None
    content: str
    content_type: ContentType = ContentType.TEXT
    
    # Page metadata
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
    page_hash: Optional[str] = None
    
    # Author/source info
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    
    # Links and references
    external_links: List[str] = Field(default_factory=list)
    internal_links: List[str] = Field(default_factory=list)
    
    # Content analysis
    word_count: Optional[int] = None
    language: Optional[str] = None
    
    # Media content
    images: List[str] = Field(default_factory=list)
    videos: List[str] = Field(default_factory=list)


class WebScrapingMessage(BaseMessage):
    """Web scraping message"""
    
    message_type: MessageType = MessageType.WEB_SCRAPING
    data: WebScrapingContent
    
    # Monitoring context
    search_query: Optional[str] = None
    monitored_vip: Optional[str] = None
    
    @validator('routing_key', always=True)
    def set_routing_key(cls, v, values):
        if not v and 'source' in values:
            return f"scraping.{values['source']}"
        return v


# Messaging Platform Message Schema
class MessagingContent(BaseModel):
    """Messaging platform content structure"""
    
    message_id: str
    channel_id: str
    channel_name: Optional[str] = None
    
    # Author info
    author_id: str
    author_username: str
    author_display_name: Optional[str] = None
    
    # Message content
    content: str
    content_type: ContentType = ContentType.TEXT
    created_at: datetime
    
    # Message metadata
    is_edited: bool = False
    is_reply: bool = False
    reply_to_id: Optional[str] = None
    
    # Attachments
    attachments: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Channel metadata
    channel_type: Optional[str] = None  # public, private, group
    member_count: Optional[int] = None


class MessagingMessage(BaseMessage):
    """Messaging platform message"""
    
    message_type: MessageType = MessageType.MESSAGING_PLATFORM
    data: MessagingContent
    
    # Monitoring context
    monitored_vip: Optional[str] = None
    monitoring_keywords: List[str] = Field(default_factory=list)
    
    @validator('routing_key', always=True)
    def set_routing_key(cls, v, values):
        if not v and 'source' in values:
            return f"messaging.{values['source']}"
        return v


# Analysis Result Schema
class ThreatAnalysisResult(BaseModel):
    """Threat analysis result structure"""
    
    analysis_id: str = Field(default_factory=lambda: str(uuid4()))
    analysis_type: str  # nlp, image, impersonation, etc.
    
    # Analysis results
    threat_detected: bool
    confidence_score: float = Field(ge=0.0, le=1.0)
    threat_level: str  # low, medium, high, critical
    
    # Detailed findings
    findings: Dict[str, Any] = Field(default_factory=dict)
    indicators: List[str] = Field(default_factory=list)
    
    # Processing info
    processed_at: datetime = Field(default_factory=datetime.utcnow)
    processing_time_ms: Optional[int] = None
    
    # Source reference
    source_message_id: str
    source_data_hash: Optional[str] = None


class ThreatAnalysisMessage(BaseMessage):
    """Threat analysis result message"""
    
    message_type: MessageType = MessageType.THREAT_ANALYSIS
    data: ThreatAnalysisResult
    
    @validator('routing_key', always=True)
    def set_routing_key(cls, v, values):
        if not v and 'data' in values:
            analysis_type = values['data'].analysis_type
            threat_level = values['data'].threat_level
            return f"analysis.{analysis_type}.{threat_level}"
        return v


# Incident Alert Schema
class IncidentData(BaseModel):
    """Incident alert data structure"""
    
    incident_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    description: str
    
    # Severity and classification
    severity: str  # low, medium, high, critical
    category: str  # impersonation, threat, coordinated_behavior, etc.
    
    # VIP context
    affected_vip: str
    vip_profile_id: Optional[str] = None
    
    # Evidence
    evidence_urls: List[str] = Field(default_factory=list)
    source_messages: List[str] = Field(default_factory=list)
    
    # Analysis summary
    threat_indicators: List[str] = Field(default_factory=list)
    confidence_score: float = Field(ge=0.0, le=1.0)
    
    # Status
    status: str = "open"  # open, investigating, resolved, false_positive
    assigned_to: Optional[str] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None


class IncidentAlertMessage(BaseMessage):
    """Incident alert message"""
    
    message_type: MessageType = MessageType.INCIDENT_ALERT
    priority: Priority = Priority.HIGH
    data: IncidentData
    
    @validator('routing_key', always=True)
    def set_routing_key(cls, v, values):
        if not v and 'data' in values:
            severity = values['data'].severity
            category = values['data'].category
            return f"incident.{severity}.{category}"
        return v


# Evidence Request Schema
class EvidenceRequest(BaseModel):
    """Evidence collection request structure"""
    
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    request_type: str  # screenshot, media_download, profile_capture
    
    # Target information
    target_url: str
    target_description: Optional[str] = None
    
    # Request parameters
    parameters: Dict[str, Any] = Field(default_factory=dict)
    
    # Context
    incident_id: Optional[str] = None
    source_message_id: Optional[str] = None
    
    # Priority and timing
    priority: Priority = Priority.MEDIUM
    deadline: Optional[datetime] = None
    
    # Status
    status: str = "pending"  # pending, processing, completed, failed
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EvidenceRequestMessage(BaseMessage):
    """Evidence collection request message"""
    
    message_type: MessageType = MessageType.EVIDENCE_REQUEST
    data: EvidenceRequest
    
    @validator('routing_key', always=True)
    def set_routing_key(cls, v, values):
        if not v and 'data' in values:
            request_type = values['data'].request_type
            return f"evidence.{request_type}"
        return v


# System Event Schema
class SystemEvent(BaseModel):
    """System event data structure"""
    
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str  # startup, shutdown, error, health_check, etc.
    
    # Event details
    component: str  # ingestion, analysis, storage, api, etc.
    description: str
    
    # Event data
    event_data: Dict[str, Any] = Field(default_factory=dict)
    
    # Severity
    level: str = "info"  # debug, info, warning, error, critical
    
    # Timestamps
    occurred_at: datetime = Field(default_factory=datetime.utcnow)


class SystemEventMessage(BaseMessage):
    """System event message"""
    
    message_type: MessageType = MessageType.SYSTEM_EVENT
    source: SourceType = SourceType.SYSTEM
    data: SystemEvent
    
    @validator('routing_key', always=True)
    def set_routing_key(cls, v, values):
        if not v and 'data' in values:
            component = values['data'].component
            level = values['data'].level
            return f"system.{component}.{level}"
        return v


# Message factory and validation
class MessageFactory:
    """Factory for creating and validating messages"""
    
    MESSAGE_TYPES = {
        MessageType.SOCIAL_MEDIA: SocialMediaMessage,
        MessageType.WEB_SCRAPING: WebScrapingMessage,
        MessageType.MESSAGING_PLATFORM: MessagingMessage,
        MessageType.THREAT_ANALYSIS: ThreatAnalysisMessage,
        MessageType.INCIDENT_ALERT: IncidentAlertMessage,
        MessageType.EVIDENCE_REQUEST: EvidenceRequestMessage,
        MessageType.SYSTEM_EVENT: SystemEventMessage,
    }
    
    @classmethod
    def create_message(cls, message_type: MessageType, **kwargs) -> BaseMessage:
        """Create a message of the specified type"""
        message_class = cls.MESSAGE_TYPES.get(message_type)
        if not message_class:
            raise ValueError(f"Unknown message type: {message_type}")
        
        return message_class(**kwargs)
    
    @classmethod
    def validate_message(cls, message_data: Dict[str, Any]) -> BaseMessage:
        """Validate and parse message data"""
        message_type = message_data.get('message_type')
        if not message_type:
            raise ValueError("Message type is required")
        
        try:
            message_type_enum = MessageType(message_type)
        except ValueError:
            raise ValueError(f"Invalid message type: {message_type}")
        
        message_class = cls.MESSAGE_TYPES.get(message_type_enum)
        if not message_class:
            raise ValueError(f"No message class for type: {message_type}")
        
        return message_class(**message_data)
    
    @classmethod
    def from_json(cls, json_str: str) -> BaseMessage:
        """Parse message from JSON string"""
        try:
            data = json.loads(json_str)
            return cls.validate_message(data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")
    
    @classmethod
    def to_json(cls, message: BaseMessage) -> str:
        """Convert message to JSON string"""
        return message.json()
    
    @classmethod
    def get_schema(cls, message_type: MessageType) -> Dict[str, Any]:
        """Get JSON schema for message type"""
        message_class = cls.MESSAGE_TYPES.get(message_type)
        if not message_class:
            raise ValueError(f"Unknown message type: {message_type}")
        
        return message_class.schema()


# Export all message types for easy import
__all__ = [
    'MessageType', 'Priority', 'SourceType', 'ContentType',
    'BaseMessage', 'SocialMediaMessage', 'WebScrapingMessage', 
    'MessagingMessage', 'ThreatAnalysisMessage', 'IncidentAlertMessage',
    'EvidenceRequestMessage', 'SystemEventMessage', 'MessageFactory'
]