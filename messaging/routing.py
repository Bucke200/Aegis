"""
Message routing logic and utilities
"""
from typing import Dict, Any, List, Optional, Callable
from enum import Enum
from .schemas import MessageType, Priority, SourceType, BaseMessage
from shared.logging_config import logger


class RoutingStrategy(str, Enum):
    """Message routing strategies"""
    DIRECT = "direct"
    TOPIC = "topic"
    FANOUT = "fanout"
    HEADERS = "headers"


class MessageRouter:
    """Handles message routing logic"""
    
    def __init__(self):
        self.routing_rules = {}
        self.exchange_configs = {}
        self._setup_default_routing()
    
    def _setup_default_routing(self):
        """Setup default routing configurations"""
        
        # Exchange configurations
        self.exchange_configs = {
            'threat_data': {
                'type': RoutingStrategy.TOPIC,
                'durable': True,
                'description': 'Raw threat monitoring data from various sources'
            },
            'analysis': {
                'type': RoutingStrategy.TOPIC,
                'durable': True,
                'description': 'Analysis results and processed threat intelligence'
            },
            'incidents': {
                'type': RoutingStrategy.TOPIC,
                'durable': True,
                'description': 'Incident alerts and notifications'
            },
            'evidence': {
                'type': RoutingStrategy.DIRECT,
                'durable': True,
                'description': 'Evidence collection requests and results'
            },
            'system': {
                'type': RoutingStrategy.TOPIC,
                'durable': True,
                'description': 'System events and monitoring'
            },
            'alerts': {
                'type': RoutingStrategy.FANOUT,
                'durable': True,
                'description': 'Critical alerts broadcast to all subscribers'
            }
        }
        
        # Default routing rules
        self.routing_rules = {
            MessageType.SOCIAL_MEDIA: {
                'exchange': 'threat_data',
                'routing_key_template': 'social.{source}',
                'priority_boost': {
                    Priority.CRITICAL: 2,
                    Priority.HIGH: 1
                }
            },
            MessageType.WEB_SCRAPING: {
                'exchange': 'threat_data',
                'routing_key_template': 'scraping.{source}',
                'priority_boost': {
                    Priority.CRITICAL: 2,
                    Priority.HIGH: 1
                }
            },
            MessageType.MESSAGING_PLATFORM: {
                'exchange': 'threat_data',
                'routing_key_template': 'messaging.{source}',
                'priority_boost': {
                    Priority.CRITICAL: 2,
                    Priority.HIGH: 1
                }
            },
            MessageType.THREAT_ANALYSIS: {
                'exchange': 'analysis',
                'routing_key_template': 'threat.{analysis_type}.{threat_level}',
                'priority_boost': {
                    Priority.CRITICAL: 3,
                    Priority.HIGH: 2
                }
            },
            MessageType.INCIDENT_ALERT: {
                'exchange': 'incidents',
                'routing_key_template': 'alert.{severity}.{category}',
                'priority_boost': {
                    Priority.CRITICAL: 5,
                    Priority.HIGH: 3
                },
                'fanout_critical': True  # Also send to alerts exchange if critical
            },
            MessageType.EVIDENCE_REQUEST: {
                'exchange': 'evidence',
                'routing_key_template': '{request_type}',
                'priority_boost': {
                    Priority.CRITICAL: 2,
                    Priority.HIGH: 1
                }
            },
            MessageType.SYSTEM_EVENT: {
                'exchange': 'system',
                'routing_key_template': '{component}.{level}',
                'priority_boost': {
                    Priority.CRITICAL: 1
                }
            }
        }
    
    def get_routing_info(self, message: BaseMessage) -> Dict[str, Any]:
        """Get routing information for a message"""
        try:
            message_type = MessageType(message.message_type)
            rule = self.routing_rules.get(message_type)
            
            if not rule:
                logger.warning(f"No routing rule for message type: {message_type}")
                return self._get_default_routing(message)
            
            # Get exchange
            exchange = rule['exchange']
            
            # Generate routing key
            routing_key = self._generate_routing_key(message, rule)
            
            # Calculate priority
            priority = self._calculate_priority(message, rule)
            
            # Check for special routing (e.g., fanout for critical incidents)
            additional_routes = self._get_additional_routes(message, rule)
            
            routing_info = {
                'exchange': exchange,
                'routing_key': routing_key,
                'priority': priority,
                'additional_routes': additional_routes,
                'exchange_type': self.exchange_configs.get(exchange, {}).get('type', 'direct')
            }
            
            logger.debug(f"Generated routing info for {message_type}: {routing_info}")
            return routing_info
            
        except Exception as e:
            logger.error(f"Error generating routing info: {e}")
            return self._get_default_routing(message)
    
    def _generate_routing_key(self, message: BaseMessage, rule: Dict[str, Any]) -> str:
        """Generate routing key from template"""
        try:
            template = rule.get('routing_key_template', '')
            
            # If message already has a routing key, use it
            if hasattr(message, 'routing_key') and message.routing_key:
                return message.routing_key
            
            # Extract values for template
            values = {
                'source': message.source.lower() if hasattr(message, 'source') else 'unknown',
                'priority': message.priority.lower() if hasattr(message, 'priority') else 'medium'
            }
            
            # Add message-specific values
            if hasattr(message, 'data'):
                data = message.data
                
                # For analysis messages
                if hasattr(data, 'analysis_type'):
                    values['analysis_type'] = data.analysis_type
                if hasattr(data, 'threat_level'):
                    values['threat_level'] = data.threat_level
                
                # For incident messages
                if hasattr(data, 'severity'):
                    values['severity'] = data.severity
                if hasattr(data, 'category'):
                    values['category'] = data.category
                
                # For evidence requests
                if hasattr(data, 'request_type'):
                    values['request_type'] = data.request_type
                
                # For system events
                if hasattr(data, 'component'):
                    values['component'] = data.component
                if hasattr(data, 'level'):
                    values['level'] = data.level
            
            # Format template
            routing_key = template.format(**values)
            return routing_key.lower()
            
        except Exception as e:
            logger.error(f"Error generating routing key: {e}")
            return f"{message.message_type}.{message.source}".lower()
    
    def _calculate_priority(self, message: BaseMessage, rule: Dict[str, Any]) -> int:
        """Calculate message priority score"""
        try:
            # Base priority mapping
            priority_map = {
                Priority.LOW: 1,
                Priority.MEDIUM: 5,
                Priority.HIGH: 8,
                Priority.CRITICAL: 10
            }
            
            base_priority = priority_map.get(message.priority, 5)
            
            # Apply priority boost from rule
            priority_boost = rule.get('priority_boost', {})
            boost = priority_boost.get(message.priority, 0)
            
            final_priority = min(base_priority + boost, 255)  # RabbitMQ max priority
            
            return final_priority
            
        except Exception as e:
            logger.error(f"Error calculating priority: {e}")
            return 5  # Default medium priority
    
    def _get_additional_routes(self, message: BaseMessage, rule: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get additional routing destinations"""
        additional_routes = []
        
        try:
            # Critical incident fanout
            if (rule.get('fanout_critical') and 
                message.priority == Priority.CRITICAL and
                message.message_type == MessageType.INCIDENT_ALERT):
                
                additional_routes.append({
                    'exchange': 'alerts',
                    'routing_key': '',  # Fanout doesn't use routing key
                    'priority': 10
                })
            
            # VIP-specific routing
            if hasattr(message, 'data') and hasattr(message.data, 'monitored_vip'):
                vip_id = getattr(message.data, 'monitored_vip', None)
                if vip_id:
                    additional_routes.append({
                        'exchange': 'vip_specific',
                        'routing_key': f'vip.{vip_id}',
                        'priority': self._calculate_priority(message, rule)
                    })
            
            return additional_routes
            
        except Exception as e:
            logger.error(f"Error getting additional routes: {e}")
            return []
    
    def _get_default_routing(self, message: BaseMessage) -> Dict[str, Any]:
        """Get default routing for unknown message types"""
        return {
            'exchange': 'default',
            'routing_key': f"{message.message_type}.{message.source}".lower(),
            'priority': 5,
            'additional_routes': [],
            'exchange_type': 'topic'
        }
    
    def add_routing_rule(self, message_type: MessageType, rule: Dict[str, Any]):
        """Add or update a routing rule"""
        self.routing_rules[message_type] = rule
        logger.info(f"Added routing rule for {message_type}: {rule}")
    
    def add_exchange_config(self, exchange_name: str, config: Dict[str, Any]):
        """Add or update exchange configuration"""
        self.exchange_configs[exchange_name] = config
        logger.info(f"Added exchange config for {exchange_name}: {config}")
    
    def get_queue_bindings(self) -> List[Dict[str, Any]]:
        """Get recommended queue bindings based on routing rules"""
        bindings = []
        
        # Standard worker queues
        worker_bindings = [
            {
                'queue': 'social_media_worker',
                'exchange': 'threat_data',
                'routing_key': 'social.*'
            },
            {
                'queue': 'web_scraping_worker',
                'exchange': 'threat_data',
                'routing_key': 'scraping.*'
            },
            {
                'queue': 'messaging_worker',
                'exchange': 'threat_data',
                'routing_key': 'messaging.*'
            },
            {
                'queue': 'analysis_worker',
                'exchange': 'threat_data',
                'routing_key': '*'
            }
        ]
        
        # Analysis result queues
        analysis_bindings = [
            {
                'queue': 'incident_processor',
                'exchange': 'analysis',
                'routing_key': 'threat.*.high'
            },
            {
                'queue': 'incident_processor',
                'exchange': 'analysis',
                'routing_key': 'threat.*.critical'
            },
            {
                'queue': 'alert_processor',
                'exchange': 'incidents',
                'routing_key': 'alert.*'
            }
        ]
        
        # Evidence collection queues
        evidence_bindings = [
            {
                'queue': 'screenshot_worker',
                'exchange': 'evidence',
                'routing_key': 'screenshot_request'
            },
            {
                'queue': 'media_download_worker',
                'exchange': 'evidence',
                'routing_key': 'media_download'
            }
        ]
        
        # System monitoring queues
        system_bindings = [
            {
                'queue': 'system_monitor',
                'exchange': 'system',
                'routing_key': '*.error'
            },
            {
                'queue': 'system_monitor',
                'exchange': 'system',
                'routing_key': '*.critical'
            }
        ]
        
        # Critical alerts fanout
        alert_bindings = [
            {
                'queue': 'critical_alerts_email',
                'exchange': 'alerts',
                'routing_key': ''  # Fanout
            },
            {
                'queue': 'critical_alerts_sms',
                'exchange': 'alerts',
                'routing_key': ''  # Fanout
            },
            {
                'queue': 'critical_alerts_slack',
                'exchange': 'alerts',
                'routing_key': ''  # Fanout
            }
        ]
        
        bindings.extend(worker_bindings)
        bindings.extend(analysis_bindings)
        bindings.extend(evidence_bindings)
        bindings.extend(system_bindings)
        bindings.extend(alert_bindings)
        
        return bindings
    
    def validate_routing_config(self) -> Dict[str, Any]:
        """Validate routing configuration"""
        validation_results = {
            'valid': True,
            'errors': [],
            'warnings': []
        }
        
        try:
            # Check that all message types have routing rules
            for message_type in MessageType:
                if message_type not in self.routing_rules:
                    validation_results['warnings'].append(
                        f"No routing rule defined for message type: {message_type}"
                    )
            
            # Check that all referenced exchanges are configured
            for message_type, rule in self.routing_rules.items():
                exchange = rule.get('exchange')
                if exchange and exchange not in self.exchange_configs:
                    validation_results['errors'].append(
                        f"Message type {message_type} references undefined exchange: {exchange}"
                    )
                    validation_results['valid'] = False
            
            # Check routing key templates
            for message_type, rule in self.routing_rules.items():
                template = rule.get('routing_key_template', '')
                if not template:
                    validation_results['warnings'].append(
                        f"No routing key template for message type: {message_type}"
                    )
            
            logger.info(f"Routing configuration validation: {validation_results}")
            return validation_results
            
        except Exception as e:
            logger.error(f"Error validating routing config: {e}")
            validation_results['valid'] = False
            validation_results['errors'].append(f"Validation error: {e}")
            return validation_results


# Global router instance
message_router = MessageRouter()