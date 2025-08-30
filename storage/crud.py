"""
CRUD operations for database models
"""
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func
from datetime import datetime, timedelta
import uuid

from .models import VIP, User, Incident, Evidence, AnalysisResult, Campaign, CollectedData
from shared.models import ThreatType, Severity, IncidentStatus, Platform
from shared.logging_config import logger


class VIPCrud:
    """CRUD operations for VIP profiles"""
    
    @staticmethod
    def create(db: Session, name: str, **kwargs) -> VIP:
        """Create a new VIP profile"""
        vip = VIP(name=name, **kwargs)
        db.add(vip)
        db.commit()
        db.refresh(vip)
        logger.info(f"Created VIP profile: {name}")
        return vip
    
    @staticmethod
    def get_by_id(db: Session, vip_id: uuid.UUID) -> Optional[VIP]:
        """Get VIP by ID"""
        return db.query(VIP).filter(VIP.id == vip_id).first()
    
    @staticmethod
    def get_by_name(db: Session, name: str) -> Optional[VIP]:
        """Get VIP by name"""
        return db.query(VIP).filter(VIP.name == name).first()
    
    @staticmethod
    def get_active(db: Session) -> List[VIP]:
        """Get all active VIP profiles"""
        return db.query(VIP).filter(VIP.monitoring_active == True).all()
    
    @staticmethod
    def update(db: Session, vip_id: uuid.UUID, **kwargs) -> Optional[VIP]:
        """Update VIP profile"""
        vip = db.query(VIP).filter(VIP.id == vip_id).first()
        if vip:
            for key, value in kwargs.items():
                setattr(vip, key, value)
            vip.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(vip)
        return vip


class IncidentCrud:
    """CRUD operations for incidents"""
    
    @staticmethod
    def create(db: Session, vip_id: uuid.UUID, platform: Platform, 
               severity: Severity, threat_type: ThreatType, 
               content: str, source_url: str, **kwargs) -> Incident:
        """Create a new incident"""
        incident = Incident(
            vip_id=vip_id,
            platform=platform,
            severity=severity,
            threat_type=threat_type,
            content=content,
            source_url=source_url,
            **kwargs
        )
        db.add(incident)
        db.commit()
        db.refresh(incident)
        logger.info(f"Created incident: {incident.id} for VIP: {vip_id}")
        return incident
    
    @staticmethod
    def get_by_id(db: Session, incident_id: uuid.UUID) -> Optional[Incident]:
        """Get incident by ID"""
        return db.query(Incident).filter(Incident.id == incident_id).first()
    
    @staticmethod
    def get_by_vip(db: Session, vip_id: uuid.UUID, 
                   limit: int = 100, offset: int = 0) -> List[Incident]:
        """Get incidents for a specific VIP"""
        return (db.query(Incident)
                .filter(Incident.vip_id == vip_id)
                .order_by(desc(Incident.detected_at))
                .offset(offset)
                .limit(limit)
                .all())
    
    @staticmethod
    def get_recent(db: Session, hours: int = 24, 
                   limit: int = 100) -> List[Incident]:
        """Get recent incidents"""
        since = datetime.utcnow() - timedelta(hours=hours)
        return (db.query(Incident)
                .filter(Incident.detected_at >= since)
                .order_by(desc(Incident.detected_at))
                .limit(limit)
                .all())
    
    @staticmethod
    def get_by_status(db: Session, status: IncidentStatus, 
                      limit: int = 100) -> List[Incident]:
        """Get incidents by status"""
        return (db.query(Incident)
                .filter(Incident.status == status)
                .order_by(desc(Incident.detected_at))
                .limit(limit)
                .all())
    
    @staticmethod
    def update_status(db: Session, incident_id: uuid.UUID, 
                      status: IncidentStatus, assigned_to: Optional[uuid.UUID] = None,
                      notes: Optional[str] = None) -> Optional[Incident]:
        """Update incident status"""
        incident = db.query(Incident).filter(Incident.id == incident_id).first()
        if incident:
            incident.status = status
            if assigned_to is not None:
                incident.assigned_to = assigned_to
            if notes is not None:
                incident.notes = notes
            incident.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(incident)
        return incident
    
    @staticmethod
    def search(db: Session, query: str, filters: Dict[str, Any] = None, 
               limit: int = 100, offset: int = 0) -> List[Incident]:
        """Search incidents with filters"""
        q = db.query(Incident)
        
        # Text search in content
        if query:
            q = q.filter(Incident.content.ilike(f"%{query}%"))
        
        # Apply filters
        if filters:
            if 'vip_id' in filters:
                q = q.filter(Incident.vip_id == filters['vip_id'])
            if 'platform' in filters:
                q = q.filter(Incident.platform == filters['platform'])
            if 'severity' in filters:
                q = q.filter(Incident.severity == filters['severity'])
            if 'threat_type' in filters:
                q = q.filter(Incident.threat_type == filters['threat_type'])
            if 'status' in filters:
                q = q.filter(Incident.status == filters['status'])
            if 'date_from' in filters:
                q = q.filter(Incident.detected_at >= filters['date_from'])
            if 'date_to' in filters:
                q = q.filter(Incident.detected_at <= filters['date_to'])
        
        return (q.order_by(desc(Incident.detected_at))
                .offset(offset)
                .limit(limit)
                .all())


class EvidenceCrud:
    """CRUD operations for evidence"""
    
    @staticmethod
    def create(db: Session, incident_id: uuid.UUID, **kwargs) -> Evidence:
        """Create evidence for an incident"""
        evidence = Evidence(incident_id=incident_id, **kwargs)
        db.add(evidence)
        db.commit()
        db.refresh(evidence)
        return evidence
    
    @staticmethod
    def get_by_incident(db: Session, incident_id: uuid.UUID) -> Optional[Evidence]:
        """Get evidence for an incident"""
        return db.query(Evidence).filter(Evidence.incident_id == incident_id).first()


class CollectedDataCrud:
    """CRUD operations for collected data"""
    
    @staticmethod
    def create(db: Session, source: Platform, author: str, content: str,
               url: str, timestamp: datetime, **kwargs) -> CollectedData:
        """Create collected data entry"""
        data = CollectedData(
            source=source,
            author=author,
            content=content,
            url=url,
            timestamp=timestamp,
            **kwargs
        )
        db.add(data)
        db.commit()
        db.refresh(data)
        return data
    
    @staticmethod
    def get_unprocessed(db: Session, limit: int = 100) -> List[CollectedData]:
        """Get unprocessed collected data"""
        return (db.query(CollectedData)
                .filter(CollectedData.processed == False)
                .order_by(CollectedData.collected_at)
                .limit(limit)
                .all())
    
    @staticmethod
    def mark_processed(db: Session, data_id: uuid.UUID) -> Optional[CollectedData]:
        """Mark collected data as processed"""
        data = db.query(CollectedData).filter(CollectedData.id == data_id).first()
        if data:
            data.processed = True
            data.processed_at = datetime.utcnow()
            db.commit()
            db.refresh(data)
        return data


class UserCrud:
    """CRUD operations for users"""
    
    @staticmethod
    def create(db: Session, username: str, email: str, 
               hashed_password: str, **kwargs) -> User:
        """Create a new user"""
        user = User(
            username=username,
            email=email,
            hashed_password=hashed_password,
            **kwargs
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Created user: {username}")
        return user
    
    @staticmethod
    def get_by_username(db: Session, username: str) -> Optional[User]:
        """Get user by username"""
        return db.query(User).filter(User.username == username).first()
    
    @staticmethod
    def get_by_email(db: Session, email: str) -> Optional[User]:
        """Get user by email"""
        return db.query(User).filter(User.email == email).first()
    
    @staticmethod
    def update_last_login(db: Session, user_id: uuid.UUID) -> Optional[User]:
        """Update user's last login time"""
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.last_login = datetime.utcnow()
            db.commit()
            db.refresh(user)
        return user