"""
Service for syncing data between PostgreSQL and Elasticsearch
"""
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import json

from .database import get_db
from .models import Incident, VIP, Campaign, CollectedData, Evidence, AnalysisResult
from .elasticsearch_client import es_client
from shared.logging_config import logger


class IndexingService:
    """Service for managing Elasticsearch indexing"""
    
    def __init__(self):
        self.es_client = es_client
    
    def incident_to_dict(self, incident: Incident, vip: VIP = None) -> Dict[str, Any]:
        """Convert incident model to Elasticsearch document"""
        doc = {
            "id": str(incident.id),
            "vip_id": str(incident.vip_id),
            "vip_name": vip.name if vip else "",
            "platform": incident.platform.value,
            "severity": incident.severity.value,
            "threat_type": incident.threat_type.value,
            "content": incident.content,
            "source_url": incident.source_url,
            "detected_at": incident.detected_at.isoformat(),
            "status": incident.status.value,
            "assigned_to": str(incident.assigned_to) if incident.assigned_to else None,
            "notes": incident.notes or "",
            "updated_at": incident.updated_at.isoformat()
        }
        
        # Add evidence if available
        if incident.evidence:
            doc["evidence"] = {
                "screenshot_url": incident.evidence.screenshot_url,
                "media_urls": incident.evidence.media_urls or [],
                "metadata": incident.evidence.metadata or {}
            }
        
        # Add analysis results
        if incident.analysis_results:
            doc["analysis_results"] = [
                {
                    "module_name": result.module_name,
                    "confidence_score": result.confidence_score,
                    "details": result.details or {}
                }
                for result in incident.analysis_results
            ]
        
        return doc
    
    def collected_data_to_dict(self, data: CollectedData) -> Dict[str, Any]:
        """Convert collected data model to Elasticsearch document"""
        return {
            "id": str(data.id),
            "source": data.source.value,
            "author": data.author,
            "content": data.content,
            "url": data.url,
            "timestamp": data.timestamp.isoformat(),
            "media_urls": data.media_urls or [],
            "metadata": data.metadata or {},
            "collected_at": data.collected_at.isoformat(),
            "processed": data.processed or False
        }
    
    def campaign_to_dict(self, campaign: Campaign, vip: VIP = None) -> Dict[str, Any]:
        """Convert campaign model to Elasticsearch document"""
        return {
            "id": str(campaign.id),
            "vip_id": str(campaign.vip_id),
            "vip_name": vip.name if vip else "",
            "detected_at": campaign.detected_at.isoformat(),
            "account_count": campaign.account_count,
            "similarity_score": campaign.similarity_score,
            "network_graph": campaign.network_graph or {},
            "status": campaign.status.value,
            "incidents": [str(ci.incident_id) for ci in campaign.campaign_incidents]
        }
    
    def index_incident(self, incident: Incident, db: Session = None) -> bool:
        """Index a single incident"""
        try:
            if not db:
                db = next(get_db())
            
            # Get VIP information
            vip = db.query(VIP).filter(VIP.id == incident.vip_id).first()
            
            # Convert to document
            doc = self.incident_to_dict(incident, vip)
            
            # Index in Elasticsearch
            return self.es_client.index_incident(doc)
            
        except Exception as e:
            logger.error(f"Failed to index incident {incident.id}: {e}")
            return False
    
    def index_collected_data(self, data: CollectedData) -> bool:
        """Index collected data"""
        try:
            doc = self.collected_data_to_dict(data)
            return self.es_client.index_collected_data(doc)
        except Exception as e:
            logger.error(f"Failed to index collected data {data.id}: {e}")
            return False
    
    def index_campaign(self, campaign: Campaign, db: Session = None) -> bool:
        """Index a campaign"""
        try:
            if not db:
                db = next(get_db())
            
            # Get VIP information
            vip = db.query(VIP).filter(VIP.id == campaign.vip_id).first()
            
            # Convert to document
            doc = self.campaign_to_dict(campaign, vip)
            
            # Index in Elasticsearch
            return self.es_client.client.index(
                index="campaigns",
                id=str(campaign.id),
                body=doc
            )
            
        except Exception as e:
            logger.error(f"Failed to index campaign {campaign.id}: {e}")
            return False
    
    def bulk_index_incidents(self, limit: int = 1000) -> int:
        """Bulk index incidents from database"""
        try:
            db = next(get_db())
            
            # Get incidents with their VIPs
            incidents = (db.query(Incident)
                        .join(VIP)
                        .limit(limit)
                        .all())
            
            indexed_count = 0
            for incident in incidents:
                if self.index_incident(incident, db):
                    indexed_count += 1
            
            logger.info(f"Bulk indexed {indexed_count} incidents")
            return indexed_count
            
        except Exception as e:
            logger.error(f"Failed to bulk index incidents: {e}")
            return 0
    
    def reindex_all(self) -> Dict[str, int]:
        """Reindex all data from database"""
        results = {
            "incidents": 0,
            "collected_data": 0,
            "campaigns": 0
        }
        
        try:
            db = next(get_db())
            
            # Reindex incidents
            incidents = db.query(Incident).all()
            for incident in incidents:
                if self.index_incident(incident, db):
                    results["incidents"] += 1
            
            # Reindex collected data
            collected_data = db.query(CollectedData).all()
            for data in collected_data:
                if self.index_collected_data(data):
                    results["collected_data"] += 1
            
            # Reindex campaigns
            campaigns = db.query(Campaign).all()
            for campaign in campaigns:
                if self.index_campaign(campaign, db):
                    results["campaigns"] += 1
            
            logger.info(f"Reindexed all data: {results}")
            return results
            
        except Exception as e:
            logger.error(f"Failed to reindex all data: {e}")
            return results
    
    def search_incidents(self, query: str = None, filters: Dict[str, Any] = None,
                        size: int = 100, from_: int = 0) -> Dict[str, Any]:
        """Search incidents using Elasticsearch"""
        return self.es_client.search_incidents(query, filters, size, from_)
    
    def get_incident_statistics(self) -> Dict[str, Any]:
        """Get incident statistics from Elasticsearch"""
        return self.es_client.get_incident_stats()
    
    def delete_incident_index(self, incident_id: str) -> bool:
        """Delete incident from index"""
        try:
            if self.es_client.client:
                self.es_client.client.delete(
                    index="incidents",
                    id=incident_id,
                    ignore=[404]
                )
                return True
        except Exception as e:
            logger.error(f"Failed to delete incident from index: {e}")
        return False
    
    def health_check(self) -> Dict[str, Any]:
        """Check Elasticsearch health and index status"""
        try:
            if not self.es_client.client:
                return {"status": "disconnected", "indices": {}}
            
            # Check cluster health
            health = self.es_client.client.cluster.health()
            
            # Check index stats
            indices_stats = {}
            for index in ["incidents", "collected_data", "campaigns"]:
                try:
                    stats = self.es_client.client.indices.stats(index=index)
                    indices_stats[index] = {
                        "doc_count": stats["indices"][index]["total"]["docs"]["count"],
                        "size": stats["indices"][index]["total"]["store"]["size_in_bytes"]
                    }
                except Exception:
                    indices_stats[index] = {"doc_count": 0, "size": 0}
            
            return {
                "status": health["status"],
                "cluster_name": health["cluster_name"],
                "indices": indices_stats
            }
            
        except Exception as e:
            logger.error(f"Elasticsearch health check failed: {e}")
            return {"status": "error", "error": str(e)}


# Global indexing service instance
indexing_service = IndexingService()