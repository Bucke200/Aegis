"""
Elasticsearch client and configuration for Aegis platform
"""
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ConnectionError, NotFoundError
from typing import Dict, List, Any, Optional
import json
from datetime import datetime

from shared.config import settings
from shared.logging_config import logger


class ElasticsearchClient:
    """Elasticsearch client wrapper for Aegis platform"""
    
    def __init__(self):
        self.client = None
        self.connect()
    
    def connect(self):
        """Connect to Elasticsearch"""
        try:
            self.client = Elasticsearch(
                [settings.elasticsearch_url],
                timeout=30,
                max_retries=3,
                retry_on_timeout=True
            )
            
            # Test connection
            if self.client.ping():
                logger.info("Connected to Elasticsearch successfully")
                self.setup_indices()
            else:
                logger.error("Failed to connect to Elasticsearch")
                
        except ConnectionError as e:
            logger.error(f"Elasticsearch connection error: {e}")
            self.client = None
    
    def setup_indices(self):
        """Create indices with proper mappings"""
        indices = {
            'incidents': self.get_incident_mapping(),
            'collected_data': self.get_collected_data_mapping(),
            'campaigns': self.get_campaign_mapping(),
            'analysis_results': self.get_analysis_mapping()
        }
        
        for index_name, mapping in indices.items():
            try:
                if not self.client.indices.exists(index=index_name):
                    self.client.indices.create(
                        index=index_name,
                        body=mapping
                    )
                    logger.info(f"Created Elasticsearch index: {index_name}")
                else:
                    logger.info(f"Elasticsearch index already exists: {index_name}")
            except Exception as e:
                logger.error(f"Failed to create index {index_name}: {e}")
    
    def get_incident_mapping(self) -> Dict[str, Any]:
        """Get mapping for incidents index"""
        return {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "analysis": {
                    "analyzer": {
                        "content_analyzer": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": ["lowercase", "stop", "snowball"]
                        }
                    }
                }
            },
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "vip_id": {"type": "keyword"},
                    "vip_name": {"type": "text", "analyzer": "content_analyzer"},
                    "platform": {"type": "keyword"},
                    "severity": {"type": "keyword"},
                    "threat_type": {"type": "keyword"},
                    "content": {
                        "type": "text",
                        "analyzer": "content_analyzer",
                        "fields": {
                            "raw": {"type": "keyword"}
                        }
                    },
                    "source_url": {"type": "keyword"},
                    "detected_at": {"type": "date"},
                    "status": {"type": "keyword"},
                    "assigned_to": {"type": "keyword"},
                    "notes": {"type": "text", "analyzer": "content_analyzer"},
                    "updated_at": {"type": "date"},
                    "evidence": {
                        "properties": {
                            "screenshot_url": {"type": "keyword"},
                            "media_urls": {"type": "keyword"},
                            "metadata": {"type": "object", "enabled": False}
                        }
                    },
                    "analysis_results": {
                        "type": "nested",
                        "properties": {
                            "module_name": {"type": "keyword"},
                            "confidence_score": {"type": "float"},
                            "details": {"type": "object", "enabled": False}
                        }
                    }
                }
            }
        }
    
    def get_collected_data_mapping(self) -> Dict[str, Any]:
        """Get mapping for collected data index"""
        return {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0
            },
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "source": {"type": "keyword"},
                    "author": {"type": "keyword"},
                    "content": {"type": "text", "analyzer": "content_analyzer"},
                    "url": {"type": "keyword"},
                    "timestamp": {"type": "date"},
                    "media_urls": {"type": "keyword"},
                    "metadata": {"type": "object", "enabled": False},
                    "collected_at": {"type": "date"},
                    "processed": {"type": "boolean"}
                }
            }
        }
    
    def get_campaign_mapping(self) -> Dict[str, Any]:
        """Get mapping for campaigns index"""
        return {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0
            },
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "vip_id": {"type": "keyword"},
                    "vip_name": {"type": "text"},
                    "detected_at": {"type": "date"},
                    "account_count": {"type": "integer"},
                    "similarity_score": {"type": "float"},
                    "network_graph": {"type": "object", "enabled": False},
                    "status": {"type": "keyword"},
                    "incidents": {"type": "keyword"}
                }
            }
        }
    
    def get_analysis_mapping(self) -> Dict[str, Any]:
        """Get mapping for analysis results index"""
        return {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0
            },
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "incident_id": {"type": "keyword"},
                    "module_name": {"type": "keyword"},
                    "confidence_score": {"type": "float"},
                    "details": {"type": "object", "enabled": False},
                    "processed_at": {"type": "date"}
                }
            }
        }
    
    def index_incident(self, incident_data: Dict[str, Any]) -> bool:
        """Index an incident document"""
        try:
            if not self.client:
                return False
                
            self.client.index(
                index="incidents",
                id=incident_data["id"],
                body=incident_data
            )
            logger.debug(f"Indexed incident: {incident_data['id']}")
            return True
        except Exception as e:
            logger.error(f"Failed to index incident: {e}")
            return False
    
    def index_collected_data(self, data: Dict[str, Any]) -> bool:
        """Index collected data document"""
        try:
            if not self.client:
                return False
                
            self.client.index(
                index="collected_data",
                id=data["id"],
                body=data
            )
            logger.debug(f"Indexed collected data: {data['id']}")
            return True
        except Exception as e:
            logger.error(f"Failed to index collected data: {e}")
            return False
    
    def search_incidents(self, query: str = None, filters: Dict[str, Any] = None,
                        size: int = 100, from_: int = 0) -> Dict[str, Any]:
        """Search incidents with query and filters"""
        try:
            if not self.client:
                return {"hits": {"hits": [], "total": {"value": 0}}}
            
            # Build search query
            search_body = {
                "size": size,
                "from": from_,
                "sort": [{"detected_at": {"order": "desc"}}],
                "query": {"bool": {"must": [], "filter": []}}
            }
            
            # Add text query
            if query:
                search_body["query"]["bool"]["must"].append({
                    "multi_match": {
                        "query": query,
                        "fields": ["content^2", "vip_name", "notes"],
                        "type": "best_fields",
                        "fuzziness": "AUTO"
                    }
                })
            else:
                search_body["query"]["bool"]["must"].append({"match_all": {}})
            
            # Add filters
            if filters:
                for field, value in filters.items():
                    if value is not None:
                        if field in ['date_from', 'date_to']:
                            # Handle date range
                            date_filter = {"range": {"detected_at": {}}}
                            if field == 'date_from':
                                date_filter["range"]["detected_at"]["gte"] = value
                            else:
                                date_filter["range"]["detected_at"]["lte"] = value
                            search_body["query"]["bool"]["filter"].append(date_filter)
                        else:
                            # Handle exact match filters
                            search_body["query"]["bool"]["filter"].append({
                                "term": {field: value}
                            })
            
            # Add highlighting
            search_body["highlight"] = {
                "fields": {
                    "content": {"fragment_size": 150, "number_of_fragments": 3},
                    "notes": {"fragment_size": 150, "number_of_fragments": 1}
                }
            }
            
            result = self.client.search(index="incidents", body=search_body)
            return result
            
        except Exception as e:
            logger.error(f"Failed to search incidents: {e}")
            return {"hits": {"hits": [], "total": {"value": 0}}}
    
    def get_incident_stats(self) -> Dict[str, Any]:
        """Get incident statistics"""
        try:
            if not self.client:
                return {}
            
            # Aggregation query for statistics
            agg_body = {
                "size": 0,
                "aggs": {
                    "by_severity": {"terms": {"field": "severity"}},
                    "by_threat_type": {"terms": {"field": "threat_type"}},
                    "by_platform": {"terms": {"field": "platform"}},
                    "by_status": {"terms": {"field": "status"}},
                    "recent_incidents": {
                        "date_histogram": {
                            "field": "detected_at",
                            "calendar_interval": "1d",
                            "min_doc_count": 0
                        }
                    }
                }
            }
            
            result = self.client.search(index="incidents", body=agg_body)
            return result.get("aggregations", {})
            
        except Exception as e:
            logger.error(f"Failed to get incident stats: {e}")
            return {}
    
    def delete_index(self, index_name: str) -> bool:
        """Delete an index"""
        try:
            if not self.client:
                return False
                
            if self.client.indices.exists(index=index_name):
                self.client.indices.delete(index=index_name)
                logger.info(f"Deleted index: {index_name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete index {index_name}: {e}")
            return False
    
    def refresh_indices(self):
        """Refresh all indices"""
        try:
            if self.client:
                self.client.indices.refresh(index="_all")
                logger.debug("Refreshed all Elasticsearch indices")
        except Exception as e:
            logger.error(f"Failed to refresh indices: {e}")


# Global Elasticsearch client instance
es_client = ElasticsearchClient()