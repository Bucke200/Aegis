"""
SQLAlchemy database models for Aegis platform
"""
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, DateTime, Boolean, Text, Float, 
    ForeignKey, JSON, Enum as SQLEnum, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from .database import Base
from shared.models import ThreatType, Severity, IncidentStatus, Platform


class VIP(Base):
    """VIP profiles table"""
    __tablename__ = "vips"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, index=True)
    official_profiles = Column(JSON, default=dict)  # Platform -> profile URL mapping
    keywords = Column(JSON, default=list)  # List of keywords to monitor
    monitoring_active = Column(Boolean, default=True, index=True)
    alert_settings = Column(JSON, default=dict)  # Alert configuration
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    incidents = relationship("Incident", back_populates="vip", cascade="all, delete-orphan")
    campaigns = relationship("Campaign", back_populates="vip", cascade="all, delete-orphan")


class User(Base):
    """System users (analysts, administrators)"""
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True))
    
    # Relationships
    assigned_incidents = relationship("Incident", back_populates="assigned_user")


class Incident(Base):
    """Main incidents table"""
    __tablename__ = "incidents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vip_id = Column(UUID(as_uuid=True), ForeignKey("vips.id"), nullable=False, index=True)
    platform = Column(SQLEnum(Platform), nullable=False, index=True)
    severity = Column(SQLEnum(Severity), nullable=False, index=True)
    threat_type = Column(SQLEnum(ThreatType), nullable=False, index=True)
    content = Column(Text, nullable=False)
    source_url = Column(Text, nullable=False)
    detected_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    status = Column(SQLEnum(IncidentStatus), default=IncidentStatus.NEW, index=True)
    assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    notes = Column(Text, default="")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    vip = relationship("VIP", back_populates="incidents")
    assigned_user = relationship("User", back_populates="assigned_incidents")
    evidence = relationship("Evidence", back_populates="incident", uselist=False, cascade="all, delete-orphan")
    analysis_results = relationship("AnalysisResult", back_populates="incident", cascade="all, delete-orphan")
    campaign_incidents = relationship("CampaignIncident", back_populates="incident")


class Evidence(Base):
    """Evidence files and metadata for incidents"""
    __tablename__ = "evidence"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False, unique=True)
    screenshot_url = Column(String(500))
    media_urls = Column(JSON, default=list)  # List of media file URLs
    meta_data = Column(JSON, default=dict)  # Additional metadata
    source_html = Column(Text)  # Raw HTML content
    captured_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    incident = relationship("Incident", back_populates="evidence")


class AnalysisResult(Base):
    """Results from analysis modules"""
    __tablename__ = "analysis_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False, index=True)
    module_name = Column(String(100), nullable=False, index=True)
    confidence_score = Column(Float, nullable=False)  # 0.0 to 1.0
    details = Column(JSON, default=dict)  # Module-specific analysis details
    processed_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    incident = relationship("Incident", back_populates="analysis_results")


class Campaign(Base):
    """Coordinated campaigns detected by the system"""
    __tablename__ = "campaigns"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vip_id = Column(UUID(as_uuid=True), ForeignKey("vips.id"), nullable=False, index=True)
    detected_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    account_count = Column(Integer, nullable=False)
    similarity_score = Column(Float, nullable=False)  # 0.0 to 1.0
    network_graph = Column(JSON, default=dict)  # Graph structure data
    status = Column(SQLEnum(IncidentStatus), default=IncidentStatus.NEW, index=True)
    
    # Relationships
    vip = relationship("VIP", back_populates="campaigns")
    campaign_incidents = relationship("CampaignIncident", back_populates="campaign", cascade="all, delete-orphan")


class CampaignIncident(Base):
    """Many-to-many relationship between campaigns and incidents"""
    __tablename__ = "campaign_incidents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False)
    
    # Relationships
    campaign = relationship("Campaign", back_populates="campaign_incidents")
    incident = relationship("Incident", back_populates="campaign_incidents")
    
    # Ensure unique campaign-incident pairs
    __table_args__ = (UniqueConstraint('campaign_id', 'incident_id', name='unique_campaign_incident'),)


class CollectedData(Base):
    """Raw collected data before processing"""
    __tablename__ = "collected_data"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(SQLEnum(Platform), nullable=False, index=True)
    author = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    url = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    media_urls = Column(JSON, default=list)
    meta_data = Column(JSON, default=dict)
    collected_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    processed = Column(Boolean, default=False, index=True)
    processed_at = Column(DateTime(timezone=True))
    
    # Index for efficient querying of unprocessed data
    __table_args__ = (
        UniqueConstraint('source', 'url', 'timestamp', name='unique_collected_data'),
    )


class SystemMetrics(Base):
    """System performance and health metrics"""
    __tablename__ = "system_metrics"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    metric_name = Column(String(100), nullable=False, index=True)
    metric_value = Column(Float, nullable=False)
    metric_type = Column(String(50), nullable=False)  # counter, gauge, histogram
    labels = Column(JSON, default=dict)  # Additional metric labels
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


async def init_database():
    """Initialize database tables"""
    try:
        from .database import engine
        # Create all tables
        Base.metadata.create_all(bind=engine)
        return True
    except Exception as e:
        from shared.logging_config import logger
        logger.error(f"Failed to initialize database: {e}")
        return False