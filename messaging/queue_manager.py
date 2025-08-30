"""
Queue management and monitoring utilities
"""
import json
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from .connection import rabbitmq_connection
from shared.logging_config import logger


@dataclass
class QueueInfo:
    """Queue information structure"""
    name: str
    messages: int
    consumers: int
    durable: bool
    auto_delete: bool


@dataclass
class ExchangeInfo:
    """Exchange information structure"""
    name: str
    type: str
    durable: bool
    auto_delete: bool


class QueueManager:
    """Manages RabbitMQ queues and exchanges"""
    
    def __init__(self):
        self.standard_queues = [
            'worker_social_media',
            'worker_web_scraping', 
            'worker_messaging',
            'analysis_queue',
            'evidence_queue',
            'alert_queue'
        ]
        
        self.standard_exchanges = [
            ('threat_data', 'topic'),
            ('analysis', 'topic'),
            ('evidence', 'direct'),
            ('alerts', 'fanout')
        ]
    
    def setup_infrastructure(self) -> bool:
        """Setup all standard queues and exchanges"""
        try:
            logger.info("Setting up message queue infrastructure...")
            
            # Setup exchanges
            for exchange_name, exchange_type in self.standard_exchanges:
                if not rabbitmq_connection.declare_exchange(exchange_name, exchange_type):
                    logger.error(f"Failed to create exchange: {exchange_name}")
                    return False
            
            # Setup queues
            for queue_name in self.standard_queues:
                if not rabbitmq_connection.declare_queue(queue_name, durable=True):
                    logger.error(f"Failed to create queue: {queue_name}")
                    return False
            
            # Setup bindings
            self._setup_bindings()
            
            logger.info("Message queue infrastructure setup completed")
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup queue infrastructure: {e}")
            return False
    
    def _setup_bindings(self):
        """Setup queue bindings to exchanges"""
        bindings = [
            # Threat data routing
            ('worker_social_media', 'threat_data', 'social.*'),
            ('worker_web_scraping', 'threat_data', 'scraping.*'),
            ('worker_messaging', 'threat_data', 'messaging.*'),
            ('analysis_queue', 'threat_data', '*'),
            
            # Analysis results routing
            ('alert_queue', 'analysis', 'incident.*'),
            ('alert_queue', 'analysis', 'threat.*'),
            
            # Evidence collection routing
            ('evidence_queue', 'evidence', 'screenshot'),
            ('evidence_queue', 'evidence', 'media_download'),
        ]
        
        for queue_name, exchange_name, routing_key in bindings:
            rabbitmq_connection.bind_queue(queue_name, exchange_name, routing_key)
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """Get statistics for all queues"""
        try:
            stats = {
                'queues': {},
                'total_messages': 0,
                'total_consumers': 0,
                'timestamp': time.time()
            }
            
            with rabbitmq_connection.get_channel() as channel:
                for queue_name in self.standard_queues:
                    try:
                        method = channel.queue_declare(queue=queue_name, passive=True)
                        message_count = method.method.message_count
                        consumer_count = method.method.consumer_count
                        
                        stats['queues'][queue_name] = {
                            'messages': message_count,
                            'consumers': consumer_count
                        }
                        
                        stats['total_messages'] += message_count
                        stats['total_consumers'] += consumer_count
                        
                    except Exception as e:
                        logger.warning(f"Could not get stats for queue {queue_name}: {e}")
                        stats['queues'][queue_name] = {
                            'messages': 0,
                            'consumers': 0,
                            'error': str(e)
                        }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get queue statistics: {e}")
            return {'error': str(e)}
    
    def purge_queue(self, queue_name: str) -> bool:
        """Purge all messages from a queue"""
        try:
            with rabbitmq_connection.get_channel() as channel:
                method = channel.queue_purge(queue=queue_name)
                purged_count = method.method.message_count
                logger.info(f"Purged {purged_count} messages from queue: {queue_name}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to purge queue {queue_name}: {e}")
            return False
    
    def delete_queue(self, queue_name: str, if_unused: bool = True, 
                    if_empty: bool = True) -> bool:
        """Delete a queue"""
        try:
            with rabbitmq_connection.get_channel() as channel:
                channel.queue_delete(
                    queue=queue_name,
                    if_unused=if_unused,
                    if_empty=if_empty
                )
                logger.info(f"Deleted queue: {queue_name}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete queue {queue_name}: {e}")
            return False
    
    def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check of message queue system"""
        try:
            health_info = {
                'status': 'healthy',
                'connection': 'active',
                'queues': {},
                'exchanges': {},
                'issues': []
            }
            
            # Check connection
            connection_health = rabbitmq_connection.health_check()
            if connection_health['status'] != 'healthy':
                health_info['status'] = 'unhealthy'
                health_info['connection'] = 'failed'
                health_info['issues'].append(f"Connection failed: {connection_health.get('error')}")
                return health_info
            
            # Check queues
            with rabbitmq_connection.get_channel() as channel:
                for queue_name in self.standard_queues:
                    try:
                        method = channel.queue_declare(queue=queue_name, passive=True)
                        health_info['queues'][queue_name] = {
                            'exists': True,
                            'messages': method.method.message_count,
                            'consumers': method.method.consumer_count
                        }
                        
                        # Check for issues
                        if method.method.message_count > 10000:
                            health_info['issues'].append(f"High message count in {queue_name}: {method.method.message_count}")
                        
                        if method.method.consumer_count == 0:
                            health_info['issues'].append(f"No consumers for queue: {queue_name}")
                            
                    except Exception as e:
                        health_info['queues'][queue_name] = {
                            'exists': False,
                            'error': str(e)
                        }
                        health_info['issues'].append(f"Queue {queue_name} not accessible: {e}")
                
                # Check exchanges
                for exchange_name, exchange_type in self.standard_exchanges:
                    try:
                        channel.exchange_declare(exchange=exchange_name, passive=True)
                        health_info['exchanges'][exchange_name] = {
                            'exists': True,
                            'type': exchange_type
                        }
                    except Exception as e:
                        health_info['exchanges'][exchange_name] = {
                            'exists': False,
                            'error': str(e)
                        }
                        health_info['issues'].append(f"Exchange {exchange_name} not accessible: {e}")
            
            # Determine overall health
            if health_info['issues']:
                health_info['status'] = 'degraded' if len(health_info['issues']) < 3 else 'unhealthy'
            
            return health_info
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                'status': 'unhealthy',
                'error': str(e)
            }
    
    def get_message_sample(self, queue_name: str, count: int = 5) -> List[Dict[str, Any]]:
        """Get sample messages from queue without consuming them"""
        try:
            messages = []
            
            with rabbitmq_connection.get_channel() as channel:
                for _ in range(count):
                    method, properties, body = channel.basic_get(queue=queue_name, auto_ack=False)
                    
                    if method is None:
                        break  # No more messages
                    
                    try:
                        message = json.loads(body.decode('utf-8'))
                        messages.append({
                            'message': message,
                            'properties': {
                                'delivery_tag': method.delivery_tag,
                                'exchange': method.exchange,
                                'routing_key': method.routing_key,
                                'message_count': method.message_count
                            }
                        })
                        
                        # Reject message to put it back in queue
                        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                        
                    except json.JSONDecodeError:
                        # Skip invalid JSON messages
                        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                        continue
            
            return messages
            
        except Exception as e:
            logger.error(f"Failed to get message sample from {queue_name}: {e}")
            return []


# Global queue manager instance
queue_manager = QueueManager()