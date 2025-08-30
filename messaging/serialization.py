"""
Message serialization and validation utilities
"""
import json
import gzip
import base64
from typing import Dict, Any, Optional, Union, Type
from datetime import datetime
from pydantic import ValidationError
from .schemas import BaseMessage, MessageFactory, MessageType
from shared.logging_config import logger


class MessageSerializer:
    """Handles message serialization and deserialization"""
    
    def __init__(self, compress_threshold: int = 1024):
        """
        Initialize message serializer
        
        Args:
            compress_threshold: Size threshold in bytes for compression
        """
        self.compress_threshold = compress_threshold
        self.encoding = 'utf-8'
    
    def serialize(self, message: BaseMessage, compress: Optional[bool] = None) -> bytes:
        """
        Serialize message to bytes
        
        Args:
            message: Message to serialize
            compress: Whether to compress (auto-detect if None)
        
        Returns:
            Serialized message bytes
        """
        try:
            # Convert to JSON
            json_str = message.json()
            json_bytes = json_str.encode(self.encoding)
            
            # Determine if compression should be used
            should_compress = compress
            if should_compress is None:
                should_compress = len(json_bytes) > self.compress_threshold
            
            if should_compress:
                # Compress and encode
                compressed = gzip.compress(json_bytes)
                # Add compression header
                return b'GZIP:' + base64.b64encode(compressed)
            else:
                # Add plain text header
                return b'JSON:' + json_bytes
                
        except Exception as e:
            logger.error(f"Failed to serialize message: {e}")
            raise ValueError(f"Serialization failed: {e}")
    
    def deserialize(self, data: bytes) -> BaseMessage:
        """
        Deserialize bytes to message
        
        Args:
            data: Serialized message bytes
        
        Returns:
            Deserialized message
        """
        try:
            # Check for compression header
            if data.startswith(b'GZIP:'):
                # Decompress
                encoded_data = data[5:]  # Remove 'GZIP:' prefix
                compressed_data = base64.b64decode(encoded_data)
                json_bytes = gzip.decompress(compressed_data)
                json_str = json_bytes.decode(self.encoding)
            elif data.startswith(b'JSON:'):
                # Plain JSON
                json_bytes = data[5:]  # Remove 'JSON:' prefix
                json_str = json_bytes.decode(self.encoding)
            else:
                # Assume plain JSON for backward compatibility
                json_str = data.decode(self.encoding)
            
            # Parse JSON and validate
            message_data = json.loads(json_str)
            return MessageFactory.validate_message(message_data)
            
        except Exception as e:
            logger.error(f"Failed to deserialize message: {e}")
            raise ValueError(f"Deserialization failed: {e}")
    
    def serialize_to_string(self, message: BaseMessage) -> str:
        """Serialize message to JSON string"""
        try:
            return message.json()
        except Exception as e:
            logger.error(f"Failed to serialize message to string: {e}")
            raise ValueError(f"String serialization failed: {e}")
    
    def deserialize_from_string(self, json_str: str) -> BaseMessage:
        """Deserialize message from JSON string"""
        try:
            return MessageFactory.from_json(json_str)
        except Exception as e:
            logger.error(f"Failed to deserialize message from string: {e}")
            raise ValueError(f"String deserialization failed: {e}")


class MessageValidator:
    """Validates message content and structure"""
    
    def __init__(self):
        self.validation_rules = {}
        self._setup_default_rules()
    
    def _setup_default_rules(self):
        """Setup default validation rules"""
        self.validation_rules = {
            MessageType.SOCIAL_MEDIA: {
                'required_fields': ['data.post_id', 'data.author_id', 'data.content'],
                'max_content_length': 10000,
                'allowed_sources': [
                    'twitter', 'facebook', 'instagram', 'linkedin'
                ]
            },
            MessageType.WEB_SCRAPING: {
                'required_fields': ['data.url', 'data.content'],
                'max_content_length': 50000,
                'allowed_sources': [
                    'pastebin', 'github', 'manual'
                ]
            },
            MessageType.MESSAGING_PLATFORM: {
                'required_fields': ['data.message_id', 'data.channel_id', 'data.content'],
                'max_content_length': 5000,
                'allowed_sources': [
                    'telegram', 'discord'
                ]
            },
            MessageType.THREAT_ANALYSIS: {
                'required_fields': ['data.analysis_type', 'data.confidence_score'],
                'confidence_range': (0.0, 1.0),
                'allowed_threat_levels': ['low', 'medium', 'high', 'critical']
            },
            MessageType.INCIDENT_ALERT: {
                'required_fields': ['data.title', 'data.affected_vip', 'data.severity'],
                'allowed_severities': ['low', 'medium', 'high', 'critical'],
                'allowed_statuses': ['open', 'investigating', 'resolved', 'false_positive']
            }
        }
    
    def validate_message(self, message: BaseMessage) -> Dict[str, Any]:
        """
        Validate message against rules
        
        Returns:
            Validation result with errors and warnings
        """
        result = {
            'valid': True,
            'errors': [],
            'warnings': []
        }
        
        try:
            message_type = MessageType(message.message_type)
            rules = self.validation_rules.get(message_type, {})
            
            # Check required fields
            self._validate_required_fields(message, rules, result)
            
            # Check content length
            self._validate_content_length(message, rules, result)
            
            # Check allowed sources
            self._validate_source(message, rules, result)
            
            # Message-specific validations
            self._validate_specific_rules(message, rules, result)
            
            # Check timestamps
            self._validate_timestamps(message, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Validation error: {e}")
            result['valid'] = False
            result['errors'].append(f"Validation exception: {e}")
            return result
    
    def _validate_required_fields(self, message: BaseMessage, rules: Dict[str, Any], 
                                 result: Dict[str, Any]):
        """Validate required fields are present"""
        required_fields = rules.get('required_fields', [])
        
        for field_path in required_fields:
            if not self._has_field(message, field_path):
                result['valid'] = False
                result['errors'].append(f"Missing required field: {field_path}")
    
    def _validate_content_length(self, message: BaseMessage, rules: Dict[str, Any],
                                result: Dict[str, Any]):
        """Validate content length limits"""
        max_length = rules.get('max_content_length')
        if not max_length:
            return
        
        # Check content field if it exists
        if hasattr(message, 'data') and hasattr(message.data, 'content'):
            content = message.data.content
            if len(content) > max_length:
                result['valid'] = False
                result['errors'].append(
                    f"Content too long: {len(content)} > {max_length}"
                )
    
    def _validate_source(self, message: BaseMessage, rules: Dict[str, Any],
                        result: Dict[str, Any]):
        """Validate message source"""
        allowed_sources = rules.get('allowed_sources')
        if not allowed_sources:
            return
        
        if message.source not in allowed_sources:
            result['warnings'].append(
                f"Unexpected source '{message.source}' for message type"
            )
    
    def _validate_specific_rules(self, message: BaseMessage, rules: Dict[str, Any],
                                result: Dict[str, Any]):
        """Validate message-specific rules"""
        
        # Confidence score validation
        if 'confidence_range' in rules and hasattr(message, 'data'):
            if hasattr(message.data, 'confidence_score'):
                score = message.data.confidence_score
                min_val, max_val = rules['confidence_range']
                if not (min_val <= score <= max_val):
                    result['valid'] = False
                    result['errors'].append(
                        f"Confidence score {score} outside range [{min_val}, {max_val}]"
                    )
        
        # Threat level validation
        if 'allowed_threat_levels' in rules and hasattr(message, 'data'):
            if hasattr(message.data, 'threat_level'):
                level = message.data.threat_level
                if level not in rules['allowed_threat_levels']:
                    result['valid'] = False
                    result['errors'].append(f"Invalid threat level: {level}")
        
        # Severity validation
        if 'allowed_severities' in rules and hasattr(message, 'data'):
            if hasattr(message.data, 'severity'):
                severity = message.data.severity
                if severity not in rules['allowed_severities']:
                    result['valid'] = False
                    result['errors'].append(f"Invalid severity: {severity}")
        
        # Status validation
        if 'allowed_statuses' in rules and hasattr(message, 'data'):
            if hasattr(message.data, 'status'):
                status = message.data.status
                if status not in rules['allowed_statuses']:
                    result['valid'] = False
                    result['errors'].append(f"Invalid status: {status}")
    
    def _validate_timestamps(self, message: BaseMessage, result: Dict[str, Any]):
        """Validate timestamp fields"""
        now = datetime.utcnow()
        
        # Check message timestamp
        if hasattr(message, 'timestamp'):
            if message.timestamp > now:
                result['warnings'].append("Message timestamp is in the future")
        
        # Check data timestamps
        if hasattr(message, 'data'):
            data = message.data
            
            # Created at should not be in future
            if hasattr(data, 'created_at'):
                if data.created_at > now:
                    result['warnings'].append("Created timestamp is in the future")
            
            # Updated at should not be before created at
            if (hasattr(data, 'created_at') and hasattr(data, 'updated_at') and
                data.updated_at and data.updated_at < data.created_at):
                result['warnings'].append("Updated timestamp is before created timestamp")
    
    def _has_field(self, obj: Any, field_path: str) -> bool:
        """Check if object has nested field"""
        try:
            parts = field_path.split('.')
            current = obj
            
            for part in parts:
                if hasattr(current, part):
                    current = getattr(current, part)
                else:
                    return False
            
            return current is not None
            
        except Exception:
            return False
    
    def add_validation_rule(self, message_type: MessageType, rules: Dict[str, Any]):
        """Add or update validation rules for message type"""
        self.validation_rules[message_type] = rules
        logger.info(f"Added validation rules for {message_type}")


class MessageEnricher:
    """Enriches messages with additional metadata"""
    
    def __init__(self):
        self.enrichment_functions = {}
        self._setup_default_enrichers()
    
    def _setup_default_enrichers(self):
        """Setup default message enrichers"""
        self.enrichment_functions = {
            MessageType.SOCIAL_MEDIA: self._enrich_social_media,
            MessageType.WEB_SCRAPING: self._enrich_web_scraping,
            MessageType.MESSAGING_PLATFORM: self._enrich_messaging,
        }
    
    def enrich_message(self, message: BaseMessage) -> BaseMessage:
        """Enrich message with additional metadata"""
        try:
            message_type = MessageType(message.message_type)
            enricher = self.enrichment_functions.get(message_type)
            
            if enricher:
                return enricher(message)
            else:
                # Apply generic enrichment
                return self._enrich_generic(message)
                
        except Exception as e:
            logger.error(f"Message enrichment failed: {e}")
            return message  # Return original message if enrichment fails
    
    def _enrich_generic(self, message: BaseMessage) -> BaseMessage:
        """Apply generic enrichment to all messages"""
        # Add processing timestamp
        if not message.metadata.get('processed_at'):
            message.metadata['processed_at'] = datetime.utcnow().isoformat()
        
        # Add message size
        message.metadata['message_size'] = len(message.json())
        
        return message
    
    def _enrich_social_media(self, message: BaseMessage) -> BaseMessage:
        """Enrich social media messages"""
        message = self._enrich_generic(message)
        
        if hasattr(message, 'data'):
            data = message.data
            
            # Calculate engagement rate
            if (hasattr(data, 'likes') and hasattr(data, 'author_followers') and
                data.author_followers and data.author_followers > 0):
                engagement_rate = (data.likes or 0) / data.author_followers
                message.metadata['engagement_rate'] = engagement_rate
            
            # Add content analysis metadata
            if hasattr(data, 'content'):
                message.metadata['word_count'] = len(data.content.split())
                message.metadata['char_count'] = len(data.content)
                message.metadata['has_urls'] = 'http' in data.content.lower()
                message.metadata['has_mentions'] = '@' in data.content
                message.metadata['has_hashtags'] = '#' in data.content
        
        return message
    
    def _enrich_web_scraping(self, message: BaseMessage) -> BaseMessage:
        """Enrich web scraping messages"""
        message = self._enrich_generic(message)
        
        if hasattr(message, 'data'):
            data = message.data
            
            # Add URL analysis
            if hasattr(data, 'url'):
                from urllib.parse import urlparse
                parsed = urlparse(data.url)
                message.metadata['domain'] = parsed.netloc
                message.metadata['path_depth'] = len([p for p in parsed.path.split('/') if p])
            
            # Add content analysis
            if hasattr(data, 'content'):
                message.metadata['content_length'] = len(data.content)
                message.metadata['line_count'] = len(data.content.split('\n'))
        
        return message
    
    def _enrich_messaging(self, message: BaseMessage) -> BaseMessage:
        """Enrich messaging platform messages"""
        message = self._enrich_generic(message)
        
        if hasattr(message, 'data'):
            data = message.data
            
            # Add message analysis
            if hasattr(data, 'content'):
                message.metadata['message_length'] = len(data.content)
                message.metadata['is_short_message'] = len(data.content) < 50
            
            # Add channel context
            if hasattr(data, 'channel_type'):
                message.metadata['is_public_channel'] = data.channel_type == 'public'
        
        return message
    
    def add_enricher(self, message_type: MessageType, enricher_func: callable):
        """Add custom enricher function"""
        self.enrichment_functions[message_type] = enricher_func
        logger.info(f"Added enricher for {message_type}")


# Global instances
message_serializer = MessageSerializer()
message_validator = MessageValidator()
message_enricher = MessageEnricher()


# Utility functions for easy access
def serialize_message(message: BaseMessage) -> bytes:
    """Serialize message to bytes"""
    return message_serializer.serialize(message)


def deserialize_message(data: bytes) -> BaseMessage:
    """Deserialize message from bytes"""
    return message_serializer.deserialize(data)


def validate_message(message: BaseMessage) -> Dict[str, Any]:
    """Validate message"""
    return message_validator.validate_message(message)


def enrich_message(message: BaseMessage) -> BaseMessage:
    """Enrich message with metadata"""
    return message_enricher.enrich_message(message)


def process_message(message: BaseMessage) -> BaseMessage:
    """Complete message processing pipeline"""
    # Enrich first
    enriched = enrich_message(message)
    
    # Validate
    validation = validate_message(enriched)
    if not validation['valid']:
        logger.warning(f"Message validation failed: {validation['errors']}")
    
    return enriched