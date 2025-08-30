"""
Message producer base class for RabbitMQ
"""
import json
import time
import uuid
from typing import Dict, Any, Optional, Union
from datetime import datetime
import pika
from .connection import rabbitmq_connection
from shared.logging_config import logger


class MessageProducer:
    """Base class for message producers"""
    
    def __init__(self, exchange_name: str = '', exchange_type: str = 'direct'):
        self.exchange_name = exchange_name
        self.exchange_type = exchange_type
        self._setup_exchange()
    
    def _setup_exchange(self):
        """Setup exchange if specified"""
        if self.exchange_name:
            try:
                rabbitmq_connection.declare_exchange(
                    self.exchange_name, 
                    self.exchange_type
                )
            except Exception as e:
                logger.warning(f"Could not setup exchange {self.exchange_name}: {e}")
                # Continue without RabbitMQ for now
    
    def publish_message(self, 
                       message: Dict[str, Any],
                       routing_key: str = '',
                       queue_name: Optional[str] = None,
                       persistent: bool = True,
                       priority: int = 0,
                       expiration: Optional[int] = None,
                       headers: Optional[Dict[str, Any]] = None) -> bool:
        """
        Publish a message to RabbitMQ
        
        Args:
            message: Message payload as dictionary
            routing_key: Routing key for message routing
            queue_name: Direct queue name (if not using exchange)
            persistent: Whether message should survive broker restart
            priority: Message priority (0-255)
            expiration: Message TTL in milliseconds
            headers: Additional message headers
        
        Returns:
            bool: True if message was published successfully
        """
        try:
            # Prepare message
            enriched_message = self._enrich_message(message)
            message_body = json.dumps(enriched_message, default=str)
            
            # Prepare properties
            properties = pika.BasicProperties(
                delivery_mode=2 if persistent else 1,
                priority=priority,
                message_id=enriched_message.get('message_id'),
                timestamp=int(time.time()),
                content_type='application/json',
                headers=headers or {}
            )
            
            if expiration:
                properties.expiration = str(expiration)
            
            # Declare queue if specified
            if queue_name:
                rabbitmq_connection.declare_queue(queue_name)
            
            # Publish message
            with rabbitmq_connection.get_channel() as channel:
                success = channel.basic_publish(
                    exchange=self.exchange_name,
                    routing_key=routing_key or queue_name or '',
                    body=message_body,
                    properties=properties,
                    mandatory=True  # Return message if unroutable
                )
                
                if success:
                    logger.info(f"Message published successfully: {enriched_message.get('message_id')}")
                    return True
                else:
                    logger.error(f"Failed to publish message: {enriched_message.get('message_id')}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error publishing message: {e}")
            return False
    
    def _enrich_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich message with metadata"""
        enriched = message.copy()
        
        # Add standard metadata if not present
        if 'message_id' not in enriched:
            enriched['message_id'] = str(uuid.uuid4())
        
        if 'timestamp' not in enriched:
            enriched['timestamp'] = datetime.utcnow().isoformat()
        
        if 'source' not in enriched:
            enriched['source'] = self.__class__.__name__
        
        return enriched
    
    def publish_batch(self, 
                     messages: list[Dict[str, Any]],
                     routing_key: str = '',
                     queue_name: Optional[str] = None,
                     **kwargs) -> Dict[str, Any]:
        """
        Publish multiple messages in batch
        
        Returns:
            Dict with success/failure counts and failed message IDs
        """
        results = {
            'total': len(messages),
            'successful': 0,
            'failed': 0,
            'failed_messages': []
        }
        
        for message in messages:
            success = self.publish_message(
                message=message,
                routing_key=routing_key,
                queue_name=queue_name,
                **kwargs
            )
            
            if success:
                results['successful'] += 1
            else:
                results['failed'] += 1
                results['failed_messages'].append(message.get('message_id', 'unknown'))
        
        logger.info(f"Batch publish completed: {results['successful']}/{results['total']} successful")
        return results


class ThreatDataProducer(MessageProducer):
    """Producer for threat monitoring data"""
    
    def __init__(self):
        super().__init__(exchange_name='threat_data', exchange_type='topic')
    
    def publish_social_media_data(self, data: Dict[str, Any], platform: str) -> bool:
        """Publish social media monitoring data"""
        routing_key = f"social.{platform}"
        return self.publish_message(
            message={
                'type': 'social_media',
                'platform': platform,
                'data': data
            },
            routing_key=routing_key
        )
    
    def publish_web_scraping_data(self, data: Dict[str, Any], source: str) -> bool:
        """Publish web scraping data"""
        routing_key = f"scraping.{source}"
        return self.publish_message(
            message={
                'type': 'web_scraping',
                'source': source,
                'data': data
            },
            routing_key=routing_key
        )
    
    def publish_messaging_data(self, data: Dict[str, Any], platform: str) -> bool:
        """Publish messaging platform data"""
        routing_key = f"messaging.{platform}"
        return self.publish_message(
            message={
                'type': 'messaging',
                'platform': platform,
                'data': data
            },
            routing_key=routing_key
        )


class AnalysisProducer(MessageProducer):
    """Producer for analysis results"""
    
    def __init__(self):
        super().__init__(exchange_name='analysis', exchange_type='topic')
    
    def publish_threat_analysis(self, analysis_result: Dict[str, Any], 
                               analysis_type: str) -> bool:
        """Publish threat analysis results"""
        routing_key = f"threat.{analysis_type}"
        return self.publish_message(
            message={
                'type': 'threat_analysis',
                'analysis_type': analysis_type,
                'result': analysis_result
            },
            routing_key=routing_key,
            priority=5  # Higher priority for analysis results
        )
    
    def publish_incident_alert(self, incident_data: Dict[str, Any], 
                              severity: str) -> bool:
        """Publish incident alerts"""
        routing_key = f"incident.{severity}"
        return self.publish_message(
            message={
                'type': 'incident_alert',
                'severity': severity,
                'incident': incident_data
            },
            routing_key=routing_key,
            priority=10,  # Highest priority for incidents
            persistent=True
        )


class EvidenceProducer(MessageProducer):
    """Producer for evidence collection tasks"""
    
    def __init__(self):
        super().__init__(exchange_name='evidence', exchange_type='direct')
    
    def request_screenshot(self, url: str, metadata: Dict[str, Any] = None) -> bool:
        """Request screenshot capture"""
        return self.publish_message(
            message={
                'type': 'screenshot_request',
                'url': url,
                'metadata': metadata or {}
            },
            routing_key='screenshot'
        )
    
    def request_media_download(self, media_url: str, 
                              metadata: Dict[str, Any] = None) -> bool:
        """Request media download"""
        return self.publish_message(
            message={
                'type': 'media_download',
                'media_url': media_url,
                'metadata': metadata or {}
            },
            routing_key='media_download'
        )


# Global producer instances - lazy initialization
threat_producer = None
analysis_producer = None
evidence_producer = None

def get_threat_producer():
    global threat_producer
    if threat_producer is None:
        threat_producer = ThreatDataProducer()
    return threat_producer

def get_analysis_producer():
    global analysis_producer
    if analysis_producer is None:
        analysis_producer = AnalysisProducer()
    return analysis_producer

def get_evidence_producer():
    global evidence_producer
    if evidence_producer is None:
        evidence_producer = EvidenceProducer()
    return evidence_producer