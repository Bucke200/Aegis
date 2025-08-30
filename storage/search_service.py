"""
High-level search service for Aegis platform
"""
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass

from .indexing_service import indexing_service
from shared.logging_config import logger


@dataclass
class SearchResult:
    """Search result container"""
    total: int
    hits: List[Dict[str, Any]]
    aggregations: Dict[str, Any]
    took: int
    
    @classmethod
    def from_es_response(cls, response: Dict[str, Any]) -> 'SearchResult':
        """Create SearchResult from Elasticsearch response"""
        return cls(
            total=response.get("hits", {}).get("total", {}).get("value", 0),
            hits=response.get("hits", {}).get("hits", []),
            aggregations=response.get("aggregations", {}),
            took=response.get("took", 0)
        )


class SearchService:
    """High-level search service"""
    
    def __init__(self):
        self.indexing_service = indexing_service
    
    def search_incidents(self, 
                        query: Optional[str] = None,
                        vip_id: Optional[str] = None,
                        platform: Optional[str] = None,
                        severity: Optional[str] = None,
                        threat_type: Optional[str] = None,
                        status: Optional[str] = None,
                        date_from: Optional[datetime] = None,
                        date_to: Optional[datetime] = None,
                        assigned_to: Optional[str] = None,
                        page: int = 1,
                        page_size: int = 20) -> SearchResult:
        """
        Search incidents with comprehensive filtering
        
        Args:
            query: Text search query
            vip_id: Filter by VIP ID
            platform: Filter by platform
            severity: Filter by severity level
            threat_type: Filter by threat type
            status: Filter by incident status
            date_from: Filter incidents from this date
            date_to: Filter incidents to this date
            assigned_to: Filter by assigned user
            page: Page number (1-based)
            page_size: Number of results per page
        
        Returns:
            SearchResult with incidents and metadata
        """
        try:
            # Build filters
            filters = {}
            if vip_id:
                filters["vip_id"] = vip_id
            if platform:
                filters["platform"] = platform
            if severity:
                filters["severity"] = severity
            if threat_type:
                filters["threat_type"] = threat_type
            if status:
                filters["status"] = status
            if assigned_to:
                filters["assigned_to"] = assigned_to
            if date_from:
                filters["date_from"] = date_from.isoformat()
            if date_to:
                filters["date_to"] = date_to.isoformat()
            
            # Calculate offset
            from_ = (page - 1) * page_size
            
            # Perform search
            response = self.indexing_service.search_incidents(
                query=query,
                filters=filters,
                size=page_size,
                from_=from_
            )
            
            return SearchResult.from_es_response(response)
            
        except Exception as e:
            logger.error(f"Failed to search incidents: {e}")
            return SearchResult(total=0, hits=[], aggregations={}, took=0)
    
    def get_recent_incidents(self, hours: int = 24, limit: int = 50) -> SearchResult:
        """Get recent incidents within specified hours"""
        date_from = datetime.utcnow() - timedelta(hours=hours)
        return self.search_incidents(
            date_from=date_from,
            page_size=limit
        )
    
    def get_high_severity_incidents(self, limit: int = 50) -> SearchResult:
        """Get high and critical severity incidents"""
        # Search for high severity incidents
        high_severity = self.search_incidents(
            severity="HIGH",
            page_size=limit // 2
        )
        
        # Search for critical severity incidents
        critical_severity = self.search_incidents(
            severity="CRITICAL",
            page_size=limit // 2
        )
        
        # Combine results
        combined_hits = critical_severity.hits + high_severity.hits
        total = critical_severity.total + high_severity.total
        
        return SearchResult(
            total=total,
            hits=combined_hits[:limit],
            aggregations={},
            took=0
        )
    
    def search_by_vip(self, vip_id: str, limit: int = 100) -> SearchResult:
        """Get all incidents for a specific VIP"""
        return self.search_incidents(
            vip_id=vip_id,
            page_size=limit
        )
    
    def search_by_content(self, content_query: str, limit: int = 50) -> SearchResult:
        """Search incidents by content similarity"""
        return self.search_incidents(
            query=content_query,
            page_size=limit
        )
    
    def get_incident_trends(self, days: int = 30) -> Dict[str, Any]:
        """Get incident trends and statistics"""
        try:
            # Get date range
            date_from = datetime.utcnow() - timedelta(days=days)
            
            # Get statistics
            stats = self.indexing_service.get_incident_statistics()
            
            # Get recent incidents for trend analysis
            recent = self.search_incidents(
                date_from=date_from,
                page_size=1000  # Get more for trend analysis
            )
            
            # Process trends
            trends = {
                "total_incidents": recent.total,
                "severity_distribution": {},
                "threat_type_distribution": {},
                "platform_distribution": {},
                "daily_counts": {}
            }
            
            # Extract aggregation data
            if "by_severity" in stats:
                trends["severity_distribution"] = {
                    bucket["key"]: bucket["doc_count"]
                    for bucket in stats["by_severity"]["buckets"]
                }
            
            if "by_threat_type" in stats:
                trends["threat_type_distribution"] = {
                    bucket["key"]: bucket["doc_count"]
                    for bucket in stats["by_threat_type"]["buckets"]
                }
            
            if "by_platform" in stats:
                trends["platform_distribution"] = {
                    bucket["key"]: bucket["doc_count"]
                    for bucket in stats["by_platform"]["buckets"]
                }
            
            if "recent_incidents" in stats:
                trends["daily_counts"] = {
                    bucket["key_as_string"]: bucket["doc_count"]
                    for bucket in stats["recent_incidents"]["buckets"]
                }
            
            return trends
            
        except Exception as e:
            logger.error(f"Failed to get incident trends: {e}")
            return {}
    
    def get_vip_summary(self, vip_id: str) -> Dict[str, Any]:
        """Get summary statistics for a specific VIP"""
        try:
            # Get all incidents for VIP
            incidents = self.search_by_vip(vip_id, limit=1000)
            
            # Calculate summary
            summary = {
                "total_incidents": incidents.total,
                "recent_incidents": 0,
                "high_severity_count": 0,
                "unresolved_count": 0,
                "platforms": set(),
                "threat_types": set()
            }
            
            # Analyze incidents
            recent_threshold = datetime.utcnow() - timedelta(days=7)
            
            for hit in incidents.hits:
                source = hit["_source"]
                
                # Count recent incidents
                detected_at = datetime.fromisoformat(source["detected_at"].replace("Z", "+00:00"))
                if detected_at >= recent_threshold:
                    summary["recent_incidents"] += 1
                
                # Count high severity
                if source["severity"] in ["HIGH", "CRITICAL"]:
                    summary["high_severity_count"] += 1
                
                # Count unresolved
                if source["status"] in ["NEW", "REVIEWING"]:
                    summary["unresolved_count"] += 1
                
                # Track platforms and threat types
                summary["platforms"].add(source["platform"])
                summary["threat_types"].add(source["threat_type"])
            
            # Convert sets to lists for JSON serialization
            summary["platforms"] = list(summary["platforms"])
            summary["threat_types"] = list(summary["threat_types"])
            
            return summary
            
        except Exception as e:
            logger.error(f"Failed to get VIP summary for {vip_id}: {e}")
            return {}
    
    def suggest_similar_incidents(self, incident_id: str, limit: int = 10) -> SearchResult:
        """Find similar incidents using content similarity"""
        try:
            # First, get the incident content
            incident_response = self.indexing_service.es_client.client.get(
                index="incidents",
                id=incident_id
            )
            
            if not incident_response["found"]:
                return SearchResult(total=0, hits=[], aggregations={}, took=0)
            
            content = incident_response["_source"]["content"]
            
            # Search for similar content
            return self.search_by_content(content, limit)
            
        except Exception as e:
            logger.error(f"Failed to find similar incidents for {incident_id}: {e}")
            return SearchResult(total=0, hits=[], aggregations={}, took=0)
    
    def health_check(self) -> Dict[str, Any]:
        """Check search service health"""
        return self.indexing_service.health_check()


# Global search service instance
search_service = SearchService()