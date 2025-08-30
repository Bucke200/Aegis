# Aegis Message Format System

The Aegis platform uses a standardized message format for all communication between components. This ensures consistent data structure, validation, routing, and processing across the entire threat monitoring system.

## Overview

The message format system provides:

- **Standardized schemas** for different message types
- **Automatic validation** and enrichment
- **Intelligent routing** based on message content
- **Serialization/deserialization** with compression
- **Type safety** with Pydantic models

## Message Types

### 1. Social Media Messages (`social_media`)

Used for data from social media platforms (Twitter, Facebook, Instagram, LinkedIn).

```python
from messaging.message_format import create_social_media_message
from messaging.schemas import SourceType, Priority

message = create_social_media_message(
    post_data={
        'post_id': '1234567890',
        'author_id': 'user123',
        'author_username': 'suspicious_user',
        'content': 'Suspicious content here...',
        'created_at': datetime.utcnow(),
        'likes': 10,
        'shares': 5
    },
    source=SourceType.TWITTER,
    monitored_vip='celebrity_name',
    keywords=['scam', 'money'],
    priority=Priority.HIGH
)
```

**Routing**: `threat_data` exchange with routing key `social.{platform}`

### 2. Web Scraping Messages (`web_scraping`)

Used for data scraped from websites (Pastebin, GitHub, forums).

```python
message = create_web_scraping_message(
    scraping_data={
        'url': 'https://pastebin.com/suspicious',
        'title': 'Leaked Information',
        'content': 'Scraped content...',
        'scraped_at': datetime.utcnow()
    },
    source=SourceType.PASTEBIN,
    search_query='celebrity personal info',
    priority=Priority.CRITICAL
)
```

**Routing**: `threat_data` exchange with routing key `scraping.{source}`

### 3. Messaging Platform Messages (`messaging_platform`)

Used for data from messaging platforms (Telegram, Discord).

```python
message = create_messaging_message(
    messaging_data={
        'message_id': 'msg123',
        'channel_id': 'channel456',
        'author_id': 'user789',
        'author_username': 'suspicious_user',
        'content': 'Threatening message...',
        'created_at': datetime.utcnow()
    },
    source=SourceType.TELEGRAM,
    monitored_vip='celebrity_name'
)
```

**Routing**: `threat_data` exchange with routing key `messaging.{platform}`

### 4. Threat Analysis Messages (`threat_analysis`)

Used for analysis results from threat detection modules.

```python
message = create_threat_analysis_message(
    analysis_data={
        'analysis_type': 'impersonation_detection',
        'threat_detected': True,
        'confidence_score': 0.92,
        'threat_level': 'critical',
        'findings': {'similarity_score': 0.95},
        'indicators': ['username_similarity', 'fake_profile']
    },
    source_message_id='original_message_id'
)
```

**Routing**: `analysis` exchange with routing key `threat.{analysis_type}.{threat_level}`

### 5. Incident Alert Messages (`incident_alert`)

Used for high-priority security incidents requiring immediate attention.

```python
message = create_incident_alert_message(
    incident_data={
        'title': 'Celebrity Impersonation Detected',
        'description': 'High-confidence impersonation with financial scam',
        'severity': 'critical',
        'category': 'impersonation',
        'affected_vip': 'celebrity_name',
        'confidence_score': 0.95,
        'evidence_urls': ['https://twitter.com/fake_account']
    }
)
```

**Routing**: `incidents` exchange with routing key `alert.{severity}.{category}`
**Special**: Critical incidents also broadcast to `alerts` fanout exchange

### 6. Evidence Request Messages (`evidence_request`)

Used for requesting evidence collection (screenshots, media downloads).

```python
message = create_evidence_request_message(
    request_data={
        'request_type': 'screenshot',
        'target_url': 'https://suspicious-site.com',
        'target_description': 'Fake celebrity website',
        'incident_id': 'incident_123'
    }
)
```

**Routing**: `evidence` exchange with routing key `{request_type}`

### 7. System Event Messages (`system_event`)

Used for system monitoring and operational events.

```python
message = create_system_event_message(
    event_data={
        'event_type': 'component_startup',
        'component': 'analysis_worker',
        'description': 'Analysis worker started successfully',
        'level': 'info'
    }
)
```

**Routing**: `system` exchange with routing key `{component}.{level}`

## Message Structure

All messages inherit from `BaseMessage` and include:

```python
{
    "message_id": "uuid4-generated-id",
    "message_type": "social_media|web_scraping|...",
    "timestamp": "2024-01-01T12:00:00Z",
    "source": "twitter|pastebin|telegram|...",
    "priority": "low|medium|high|critical",
    "routing_key": "auto-generated-routing-key",
    "exchange": "target-exchange",
    "metadata": {
        "processed_at": "2024-01-01T12:00:01Z",
        "message_size": 1024,
        "enrichment_data": "..."
    },
    "data": {
        // Message-specific content
    }
}
```

## Message Processing Pipeline

1. **Creation**: Message created with type-specific factory function
2. **Enrichment**: Automatic metadata addition (timestamps, content analysis, etc.)
3. **Validation**: Schema validation and business rule checks
4. **Routing**: Automatic routing key and exchange determination
5. **Serialization**: Compression and encoding for transport
6. **Transport**: Delivery via RabbitMQ message queue

## Usage Examples

### Creating Messages

```python
from messaging.message_format import create_social_media_message
from messaging.schemas import SourceType, Priority

# Create a social media message
message = create_social_media_message(
    post_data={
        'post_id': 'tweet_123',
        'author_id': 'user_456',
        'author_username': 'suspicious_account',
        'content': 'Send me Bitcoin and I will double it!',
        'created_at': datetime.utcnow()
    },
    source=SourceType.TWITTER,
    monitored_vip='real_celebrity',
    priority=Priority.HIGH
)
```

### Processing Raw Messages

```python
from messaging.message_format import process_raw_message

# Process raw message data
raw_data = {
    'message_type': 'social_media',
    'source': 'twitter',
    'data': {
        'post_id': 'tweet_123',
        'author_id': 'user_456',
        'content': 'Raw message content'
    }
}

message = process_raw_message(raw_data)
```

### Serialization

```python
from messaging.serialization import serialize_message, deserialize_message

# Serialize for transport
serialized = serialize_message(message)

# Deserialize from transport
deserialized = deserialize_message(serialized)
```

### Routing Information

```python
from messaging.message_format import get_message_routing

# Get routing information
routing = get_message_routing(message)
print(f"Exchange: {routing['exchange']}")
print(f"Routing Key: {routing['routing_key']}")
print(f"Priority: {routing['priority']}")
```

## CLI Tools

### Testing

```bash
# Run comprehensive tests
make format-test
# or
python -m messaging.format_cli test

# Test with realistic examples
python -m messaging.format_cli examples
```

### Schema Management

```bash
# Show all schemas
make format-schemas
# or
python -m messaging.format_cli schemas

# Show specific schema
python -m messaging.format_cli schemas --type social_media
```

### Routing Configuration

```bash
# Show routing configuration
make format-routing
# or
python -m messaging.format_cli routing
```

### Message Creation

```bash
# Create test message
python -m messaging.format_cli create \
    --type social_media \
    --source twitter \
    --priority high \
    --data '{"post_id": "test123", "author_id": "user456", "content": "Test content"}'
```

### Template Generation

```bash
# Generate message template
python -m messaging.format_cli template --message-type social_media
```

### File Validation

```bash
# Validate messages from JSON file
python -m messaging.format_cli validate-file --file messages.json
```

## Configuration

### Validation Rules

Validation rules are automatically applied based on message type:

- **Required fields**: Ensures critical fields are present
- **Content length**: Limits content size to prevent abuse
- **Source validation**: Checks source compatibility with message type
- **Timestamp validation**: Ensures timestamps are reasonable
- **Business rules**: Message-specific validation (e.g., confidence scores 0-1)

### Routing Rules

Routing is automatically determined based on:

- **Message type**: Determines target exchange
- **Source platform**: Included in routing key
- **Priority level**: Affects message priority score
- **Content analysis**: May trigger additional routing (e.g., VIP-specific queues)

### Enrichment

Messages are automatically enriched with:

- **Processing metadata**: Timestamps, message size, processing info
- **Content analysis**: Word count, character count, URL detection
- **Social media metrics**: Engagement rates, follower ratios
- **Security indicators**: Suspicious patterns, threat indicators

## Integration

### With Message Queue System

```python
from messaging.producer import threat_producer
from messaging.message_format import create_social_media_message

# Create and publish message
message = create_social_media_message(...)
threat_producer.publish_social_media_data(
    message.data.dict(), 
    message.source
)
```

### With Analysis Modules

```python
from messaging.consumer import AnalysisConsumer
from messaging.message_format import create_threat_analysis_message

def analyze_message(message_data, message_type):
    # Perform analysis
    analysis_result = perform_threat_analysis(message_data)
    
    # Create analysis message
    analysis_message = create_threat_analysis_message(
        analysis_data=analysis_result,
        source_message_id=message_data['message_id']
    )
    
    return analysis_message
```

## Best Practices

1. **Always use factory functions** for message creation
2. **Validate messages** before processing
3. **Include relevant metadata** for monitoring and debugging
4. **Use appropriate priority levels** for message routing
5. **Handle serialization errors** gracefully
6. **Monitor message format statistics** for system health
7. **Keep message content reasonable** in size
8. **Use structured logging** for message processing events

## Error Handling

The message format system includes comprehensive error handling:

- **Schema validation errors**: Clear error messages for invalid data
- **Serialization errors**: Graceful handling of malformed data
- **Routing errors**: Fallback routing for unknown message types
- **Processing errors**: Detailed logging and error tracking

## Performance Considerations

- **Message compression**: Automatic compression for large messages
- **Batch processing**: Support for batch message operations
- **Memory efficiency**: Streaming serialization for large datasets
- **Caching**: Schema and routing rule caching for performance

## Security

- **Input validation**: All message content is validated
- **Size limits**: Protection against oversized messages
- **Content sanitization**: Automatic sanitization of dangerous content
- **Audit logging**: All message processing is logged for security auditing