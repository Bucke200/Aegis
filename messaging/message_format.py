"""
Unified message format utilities and integration
"""
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
import json
from .schemas import (
    MessageFactory, MessageType, Priority, SourceType, ContentType,
    BaseMessage, SocialMediaMessage, WebScrapingMessage, MessagingMessage,
    ThreatAnalysisMessage, IncidentAlertMessage, EvidenceRequestMessage,
    SystemEventMessage
)
from .routing import message_router
from .serialization import (
    message_serializer, message_validator, message_enricher,
    serialize_message, deserialize_message, validate_message, enrich_message
)
from shared.logging_config import logger


class MessageFormatManager:
    """Central manager for standardized message format operations"""
    
    def __init__(self):
        self.factory = MessageFactory()
        self.router = message_router
        self.serializer = message_serializer
        self.validator = message_validator
        self.enricher = message_enricher
    
    def create_social_media_message(self, 
                                   post_data: Dict[str, Any],
                                   source: SourceType,
                                   monitored_vip: Optional[str] = None,
                                   keywords: List[str] = None,
                                   priority: Priority = Priority.MEDIUM) -> SocialMediaMessage:
        """Create a standardized social media message"""
        try:
            from .schemas import SocialMediaContent
            
            # Create content object
            content = SocialMediaContent(**post_data)
            
            # Create message
            message = SocialMediaMessage(
                source=source,
                priority=priority,
                data=content,
                monitored_vip=monitored_vip,
                monitoring_keywords=keywords or []
            )
            
            # Enrich and validate
            message = self.enricher.enrich_message(message)
            validation = self.validator.validate_message(message)
            
            if not validation['valid']:
                logger.warning(f"Social media message validation issues: {validation['errors']}")
            
            return message
            
        except Exception as e:
            logger.error(f"Failed to create social media message: {e}")
            raise ValueError(f"Message creation failed: {e}")
    
    def create_web_scraping_message(self,
                                   scraping_data: Dict[str, Any],
                                   source: SourceType,
                                   search_query: Optional[str] = None,
                                   monitored_vip: Optional[str] = None,
                                   priority: Priority = Priority.MEDIUM) -> WebScrapingMessage:
        """Create a standardized web scraping message"""
        try:
            from .schemas import WebScrapingContent
            
            # Create content object
            content = WebScrapingContent(**scraping_data)
            
            # Create message
            message = WebScrapingMessage(
                source=source,
                priority=priority,
                data=content,
                search_query=search_query,
                monitored_vip=monitored_vip
            )
            
            # Enrich and validate
            message = self.enricher.enrich_message(message)
            validation = self.validator.validate_message(message)
            
            if not validation['valid']:
                logger.warning(f"Web scraping message validation issues: {validation['errors']}")
            
            return message
            
        except Exception as e:
            logger.error(f"Failed to create web scraping message: {e}")
            raise ValueError(f"Message creation failed: {e}")
    
    def create_messaging_message(self,
                                messaging_data: Dict[str, Any],
                                source: SourceType,
                                monitored_vip: Optional[str] = None,
                                keywords: List[str] = None,
                                priority: Priority = Priority.MEDIUM) -> MessagingMessage:
        """Create a standardized messaging platform message"""
        try:
            from .schemas import MessagingContent
            
            # Create content object
            content = MessagingContent(**messaging_data)
            
            # Create message
            message = MessagingMessage(
                source=source,
                priority=priority,
                data=content,
                monitored_vip=monitored_vip,
                monitoring_keywords=keywords or []
            )
            
            # Enrich and validate
            message = self.enricher.enrich_message(message)
            validation = self.validator.validate_message(message)
            
            if not validation['valid']:
                logger.warning(f"Messaging message validation issues: {validation['errors']}")
            
            return message
            
        except Exception as e:
            logger.error(f"Failed to create messaging message: {e}")
            raise ValueError(f"Message creation failed: {e}")
    
    def create_threat_analysis_message(self,
                                      analysis_data: Dict[str, Any],
                                      source_message_id: str,
                                      priority: Priority = Priority.HIGH) -> ThreatAnalysisMessage:
        """Create a standardized threat analysis message"""
        try:
            from .schemas import ThreatAnalysisResult
            
            # Ensure required fields
            analysis_data['source_message_id'] = source_message_id
            
            # Create analysis result object
            result = ThreatAnalysisResult(**analysis_data)
            
            # Create message
            message = ThreatAnalysisMessage(
                source=SourceType.SYSTEM,
                priority=priority,
                data=result
            )
            
            # Enrich and validate
            message = self.enricher.enrich_message(message)
            validation = self.validator.validate_message(message)
            
            if not validation['valid']:
                logger.warning(f"Threat analysis message validation issues: {validation['errors']}")
            
            return message
            
        except Exception as e:
            logger.error(f"Failed to create threat analysis message: {e}")
            raise ValueError(f"Message creation failed: {e}")
    
    def create_incident_alert_message(self,
                                     incident_data: Dict[str, Any],
                                     priority: Priority = Priority.CRITICAL) -> IncidentAlertMessage:
        """Create a standardized incident alert message"""
        try:
            from .schemas import IncidentData
            
            # Create incident data object
            incident = IncidentData(**incident_data)
            
            # Create message
            message = IncidentAlertMessage(
                source=SourceType.SYSTEM,
                priority=priority,
                data=incident
            )
            
            # Enrich and validate
            message = self.enricher.enrich_message(message)
            validation = self.validator.validate_message(message)
            
            if not validation['valid']:
                logger.warning(f"Incident alert message validation issues: {validation['errors']}")
            
            return message
            
        except Exception as e:
            logger.error(f"Failed to create incident alert message: {e}")
            raise ValueError(f"Message creation failed: {e}")
    
    def create_evidence_request_message(self,
                                       request_data: Dict[str, Any],
                                       priority: Priority = Priority.MEDIUM) -> EvidenceRequestMessage:
        """Create a standardized evidence request message"""
        try:
            from .schemas import EvidenceRequest
            
            # Create evidence request object
            request = EvidenceRequest(**request_data)
            
            # Create message
            message = EvidenceRequestMessage(
                source=SourceType.SYSTEM,
                priority=priority,
                data=request
            )
            
            # Enrich and validate
            message = self.enricher.enrich_message(message)
            validation = self.validator.validate_message(message)
            
            if not validation['valid']:
                logger.warning(f"Evidence request message validation issues: {validation['errors']}")
            
            return message
            
        except Exception as e:
            logger.error(f"Failed to create evidence request message: {e}")
            raise ValueError(f"Message creation failed: {e}")
    
    def create_system_event_message(self,
                                   event_data: Dict[str, Any],
                                   priority: Priority = Priority.LOW) -> SystemEventMessage:
        """Create a standardized system event message"""
        try:
            from .schemas import SystemEvent
            
            # Create system event object
            event = SystemEvent(**event_data)
            
            # Create message
            message = SystemEventMessage(
                source=SourceType.SYSTEM,
                priority=priority,
                data=event
            )
            
            # Enrich and validate
            message = self.enricher.enrich_message(message)
            validation = self.validator.validate_message(message)
            
            if not validation['valid']:
                logger.warning(f"System event message validation issues: {validation['errors']}")
            
            return message
            
        except Exception as e:
            logger.error(f"Failed to create system event message: {e}")
            raise ValueError(f"Message creation failed: {e}")
    
    def process_raw_message(self, raw_data: Dict[str, Any]) -> BaseMessage:
        """Process raw message data into standardized format"""
        try:
            # Validate and create message
            message = self.factory.validate_message(raw_data)
            
            # Enrich message
            message = self.enricher.enrich_message(message)
            
            # Validate enriched message
            validation = self.validator.validate_message(message)
            if not validation['valid']:
                logger.warning(f"Raw message processing validation issues: {validation['errors']}")
            
            return message
            
        except Exception as e:
            logger.error(f"Failed to process raw message: {e}")
            raise ValueError(f"Raw message processing failed: {e}")
    
    def get_routing_info(self, message: BaseMessage) -> Dict[str, Any]:
        """Get routing information for a message"""
        return self.router.get_routing_info(message)
    
    def serialize_for_transport(self, message: BaseMessage) -> bytes:
        """Serialize message for transport"""
        return self.serializer.serialize(message)
    
    def deserialize_from_transport(self, data: bytes) -> BaseMessage:
        """Deserialize message from transport"""
        return self.serializer.deserialize(data)
    
    def get_message_schema(self, message_type: MessageType) -> Dict[str, Any]:
        """Get JSON schema for message type"""
        return self.factory.get_schema(message_type)
    
    def validate_message_format(self, message: BaseMessage) -> Dict[str, Any]:
        """Validate message format"""
        return self.validator.validate_message(message)
    
    def get_format_statistics(self) -> Dict[str, Any]:
        """Get statistics about message format usage"""
        # This would be implemented with actual usage tracking
        return {
            'supported_message_types': len(MessageType),
            'supported_sources': len(SourceType),
            'supported_content_types': len(ContentType),
            'validation_rules_count': len(self.validator.validation_rules),
            'routing_rules_count': len(self.router.routing_rules),
            'exchange_configs_count': len(self.router.exchange_configs)
        }


class MessageFormatUtils:
    """Utility functions for message format operations"""
    
    @staticmethod
    def extract_vip_mentions(content: str) -> List[str]:
        """Extract VIP mentions from content"""
        # Simple implementation - can be enhanced with NLP
        import re
        mentions = re.findall(r'@(\w+)', content)
        return mentions
    
    @staticmethod
    def extract_keywords(content: str, keyword_list: List[str]) -> List[str]:
        """Extract matching keywords from content"""
        content_lower = content.lower()
        found_keywords = []
        
        for keyword in keyword_list:
            if keyword.lower() in content_lower:
                found_keywords.append(keyword)
        
        return found_keywords
    
    @staticmethod
    def calculate_threat_score(indicators: List[str], weights: Dict[str, float] = None) -> float:
        """Calculate threat score based on indicators"""
        if not indicators:
            return 0.0
        
        default_weights = {
            'impersonation': 0.8,
            'threat_language': 0.7,
            'coordinated_behavior': 0.6,
            'suspicious_profile': 0.5,
            'fake_media': 0.9
        }
        
        weights = weights or default_weights
        total_score = 0.0
        
        for indicator in indicators:
            weight = weights.get(indicator, 0.3)  # Default weight for unknown indicators
            total_score += weight
        
        # Normalize to 0-1 range
        return min(total_score / len(indicators), 1.0)
    
    @staticmethod
    def format_message_summary(message: BaseMessage) -> str:
        """Create a human-readable summary of the message"""
        try:
            summary_parts = [
                f"Type: {message.message_type}",
                f"Source: {message.source}",
                f"Priority: {message.priority}",
                f"Timestamp: {message.timestamp.isoformat()}"
            ]
            
            # Add message-specific details
            if hasattr(message, 'data'):
                data = message.data
                
                if hasattr(data, 'content'):
                    content_preview = data.content[:100] + "..." if len(data.content) > 100 else data.content
                    summary_parts.append(f"Content: {content_preview}")
                
                if hasattr(data, 'url'):
                    summary_parts.append(f"URL: {data.url}")
                
                if hasattr(data, 'author_username'):
                    summary_parts.append(f"Author: {data.author_username}")
                
                if hasattr(data, 'severity'):
                    summary_parts.append(f"Severity: {data.severity}")
                
                if hasattr(data, 'threat_level'):
                    summary_parts.append(f"Threat Level: {data.threat_level}")
            
            return " | ".join(summary_parts)
            
        except Exception as e:
            logger.error(f"Failed to format message summary: {e}")
            return f"Message {message.message_id} (format error)"
    
    @staticmethod
    def convert_legacy_format(legacy_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert legacy message format to standardized format"""
        # This would implement conversion from old message formats
        # For now, return as-is
        return legacy_data
    
    @staticmethod
    def export_message_schemas() -> Dict[str, Any]:
        """Export all message schemas for documentation"""
        schemas = {}
        
        for message_type in MessageType:
            try:
                schema = MessageFactory.get_schema(message_type)
                schemas[message_type.value] = schema
            except Exception as e:
                logger.error(f"Failed to get schema for {message_type}: {e}")
        
        return schemas


# Global message format manager
message_format_manager = MessageFormatManager()

# Convenience functions
def create_social_media_message(**kwargs) -> SocialMediaMessage:
    """Create social media message"""
    return message_format_manager.create_social_media_message(**kwargs)

def create_web_scraping_message(**kwargs) -> WebScrapingMessage:
    """Create web scraping message"""
    return message_format_manager.create_web_scraping_message(**kwargs)

def create_messaging_message(**kwargs) -> MessagingMessage:
    """Create messaging platform message"""
    return message_format_manager.create_messaging_message(**kwargs)

def create_threat_analysis_message(**kwargs) -> ThreatAnalysisMessage:
    """Create threat analysis message"""
    return message_format_manager.create_threat_analysis_message(**kwargs)

def create_incident_alert_message(**kwargs) -> IncidentAlertMessage:
    """Create incident alert message"""
    return message_format_manager.create_incident_alert_message(**kwargs)

def create_evidence_request_message(**kwargs) -> EvidenceRequestMessage:
    """Create evidence request message"""
    return message_format_manager.create_evidence_request_message(**kwargs)

def create_system_event_message(**kwargs) -> SystemEventMessage:
    """Create system event message"""
    return message_format_manager.create_system_event_message(**kwargs)

def process_raw_message(raw_data: Dict[str, Any]) -> BaseMessage:
    """Process raw message data"""
    return message_format_manager.process_raw_message(raw_data)

def get_message_routing(message: BaseMessage) -> Dict[str, Any]:
    """Get message routing information"""
    return message_format_manager.get_routing_info(message)