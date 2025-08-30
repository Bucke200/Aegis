# Aegis Social Media API Connectors

The Aegis platform includes comprehensive social media API connectors for monitoring threats across multiple platforms. These connectors provide real-time streaming, search capabilities, and standardized data processing for threat detection.

## Supported Platforms

### 1. Twitter/X API Connector
- **Real-time streaming** with keyword filtering
- **Search API** for historical and recent tweets
- **User timeline** monitoring
- **Rate limit handling** (300 requests per 15 minutes)
- **Engagement metrics** (likes, retweets, replies, views)

### 2. Meta Graph API Connector (Facebook/Instagram)
- **Facebook page monitoring** and search
- **Instagram Business API** integration
- **Hashtag tracking** for Instagram
- **Public content access** (limited by API restrictions)
- **Rate limit handling** (200 requests per hour)

### 3. LinkedIn API Connector
- **Organization posts** monitoring
- **Professional network** content access
- **Company search** functionality
- **Rate limit handling** (500 requests per day)
- **Business-focused** threat detection

## Architecture

### Base Connector Class
All connectors inherit from `BaseSocialMediaConnector` which provides:

- **Standardized interface** for all platforms
- **Rate limiting** with automatic backoff
- **Error handling** and retry logic
- **Message processing** and publishing
- **Health monitoring** and metrics
- **Async/await** support for high performance

### Connector Manager
The `SocialMediaConnectorManager` coordinates multiple connectors:

- **Multi-platform monitoring** with unified interface
- **Task management** for monitoring campaigns
- **Load balancing** across connectors
- **Centralized configuration** and status monitoring

## Configuration

### Environment Variables

Create a `.env` file with your API credentials:

```bash
# Twitter/X API
TWITTER_BEARER_TOKEN=your_bearer_token_here
TWITTER_API_KEY=your_api_key_here
TWITTER_API_SECRET=your_api_secret_here
TWITTER_ACCESS_TOKEN=your_access_token_here
TWITTER_ACCESS_TOKEN_SECRET=your_access_token_secret_here

# Meta (Facebook/Instagram) API
FACEBOOK_ACCESS_TOKEN=your_facebook_token_here
FACEBOOK_APP_ID=your_app_id_here
FACEBOOK_APP_SECRET=your_app_secret_here
INSTAGRAM_BUSINESS_ACCOUNT_ID=your_instagram_business_id_here

# LinkedIn API
LINKEDIN_ACCESS_TOKEN=your_linkedin_token_here
LINKEDIN_ORGANIZATION_ID=your_organization_id_here
LINKEDIN_CLIENT_ID=your_client_id_here
LINKEDIN_CLIENT_SECRET=your_client_secret_here
```

### API Credentials Setup

#### Twitter/X API
1. Visit [Twitter Developer Portal](https://developer.twitter.com/)
2. Create a new app and generate API keys
3. Enable API v2 access for enhanced features
4. Copy Bearer Token for authentication

#### Meta Graph API
1. Visit [Facebook Developers](https://developers.facebook.com/)
2. Create a new app and configure Graph API
3. Generate long-lived access token
4. For Instagram: Connect Instagram Business Account

#### LinkedIn API
1. Visit [LinkedIn Developer Portal](https://developer.linkedin.com/)
2. Create a new app with required permissions
3. Generate access token with appropriate scopes
4. Configure organization access if needed

## Usage Examples

### Basic Connector Usage

```python
from ingestion.twitter_connector import create_twitter_connector
from ingestion.meta_connector import create_facebook_connector
from ingestion.linkedin_connector import create_linkedin_connector

# Initialize connectors
twitter = create_twitter_connector()
facebook = create_facebook_connector()
linkedin = create_linkedin_connector()

# Start connectors
await twitter.start()
await facebook.start()
await linkedin.start()

# Search for posts
async for post in twitter.search_posts("celebrity scam", limit=50):
    print(f"Found post: {post['content'][:100]}...")

# Monitor user posts
async for post in twitter.get_user_posts("suspicious_account", limit=20):
    print(f"User post: {post['content'][:100]}...")
```

### Connector Manager Usage

```python
from ingestion.connector_manager import connector_manager, MonitoringMode
from messaging.schemas import SourceType

# Initialize all available connectors
await connector_manager.initialize()

# Start monitoring task
await connector_manager.start_monitoring(
    task_id="celebrity_protection",
    keywords=["celebrity_name", "scam", "threat"],
    vips=["celebrity_name", "public_figure"],
    platforms=[SourceType.TWITTER, SourceType.FACEBOOK],
    mode=MonitoringMode.HYBRID,
    duration=3600  # 1 hour
)

# Check status
status = connector_manager.get_status()
print(f"Active connectors: {status['active_connectors']}")
print(f"Active tasks: {status['active_tasks']}")

# Stop monitoring
await connector_manager.stop_monitoring("celebrity_protection")
```

### Real-time Streaming

```python
async def handle_stream_message(message_data):
    """Handle incoming stream message"""
    print(f"New message: {message_data['content']}")
    
    # Check for threats
    if any(word in message_data['content'].lower() 
           for word in ['scam', 'threat', 'hack']):
        print("⚠️ Potential threat detected!")

# Start streaming
await twitter.stream_real_time(
    keywords=["celebrity_name", "bitcoin_scam"],
    callback=handle_stream_message
)
```

## CLI Management

### Initialize Connectors

```bash
# Initialize all available connectors
make connectors-init

# Initialize specific platforms
python -m ingestion.connector_cli init --platforms twitter,facebook
```

### Monitor Status

```bash
# Check connector status
make connectors-status

# Check connector health
make connectors-health
```

### Start Monitoring

```bash
# Start monitoring task
python -m ingestion.connector_cli start-monitoring \
    --task-id "vip_protection" \
    --keywords "celebrity_name,scam,threat" \
    --vips "celebrity_name" \
    --platforms "twitter,facebook" \
    --mode "hybrid" \
    --duration 3600
```

### Test Functionality

```bash
# Test search functionality
python -m ingestion.connector_cli test-search \
    --platform twitter \
    --query "celebrity scam"

# Test user posts
python -m ingestion.connector_cli test-user-posts \
    --platform twitter \
    --user-id "suspicious_account"
```

### Configuration Template

```bash
# Generate configuration template
python -m ingestion.connector_cli config-template --output .env.template
```

## Monitoring Modes

### 1. Stream Only (`stream_only`)
- **Real-time streaming** for supported platforms (Twitter)
- **Immediate detection** of new content
- **High throughput** for active monitoring
- **Best for**: Active threat monitoring, breaking news

### 2. Search Only (`search_only`)
- **Periodic searches** for keywords and VIPs
- **Historical content** access
- **Lower API usage** than streaming
- **Best for**: Research, historical analysis

### 3. Hybrid (`hybrid`)
- **Combines streaming and search**
- **Real-time for Twitter**, polling for others
- **Comprehensive coverage** across platforms
- **Best for**: Complete threat monitoring

### 4. Polling (`polling`)
- **Regular polling** of all platforms
- **Consistent behavior** across platforms
- **Configurable intervals**
- **Best for**: Batch processing, rate limit management

## Message Processing

### Standardized Format
All connectors produce messages in standardized format:

```python
{
    "post_id": "platform_specific_id",
    "author_id": "author_identifier",
    "author_username": "username",
    "author_display_name": "Display Name",
    "content": "Post content text",
    "created_at": "2024-01-01T12:00:00Z",
    "url": "https://platform.com/post/url",
    "likes": 100,
    "shares": 50,
    "comments": 25,
    "author_followers": 1000,
    "author_verified": false,
    "hashtags": ["tag1", "tag2"],
    "mentions": ["@user1", "@user2"],
    "media_urls": ["https://media.url"]
}
```

### Message Routing
Messages are automatically routed through the message queue system:

- **Exchange**: `threat_data`
- **Routing Key**: `social.{platform}` (e.g., `social.twitter`)
- **Priority**: Based on content analysis and VIP involvement
- **Enrichment**: Automatic metadata addition

## Rate Limiting

### Twitter/X API
- **Search**: 300 requests per 15 minutes
- **User Timeline**: 900 requests per 15 minutes
- **Streaming**: 1 concurrent connection
- **Automatic backoff** when limits reached

### Meta Graph API
- **General**: 200 requests per hour
- **Search**: 5 requests per minute
- **Usage-based throttling** with percentage tracking

### LinkedIn API
- **General**: 500 requests per day
- **Search**: 100 searches per day
- **Daily reset** at midnight UTC

## Error Handling

### Connection Errors
- **Automatic reconnection** with exponential backoff
- **Circuit breaker** pattern for persistent failures
- **Graceful degradation** when platforms unavailable

### API Errors
- **Rate limit handling** with automatic waiting
- **Authentication refresh** for expired tokens
- **Detailed error logging** for debugging

### Data Processing Errors
- **Validation errors** logged but don't stop processing
- **Malformed data** handled gracefully
- **Partial failures** don't affect other messages

## Performance Optimization

### Async Processing
- **Non-blocking I/O** for all API calls
- **Concurrent processing** of multiple platforms
- **Efficient memory usage** with generators

### Caching
- **Rate limit info** cached to avoid unnecessary checks
- **User information** cached to reduce API calls
- **Search results** deduplicated

### Batching
- **Batch message processing** for efficiency
- **Bulk API operations** where supported
- **Configurable batch sizes**

## Security Considerations

### API Key Management
- **Environment variables** for credential storage
- **No hardcoded credentials** in source code
- **Secure token refresh** mechanisms

### Data Privacy
- **Minimal data collection** - only what's needed
- **No storage of sensitive user data**
- **Compliance with platform terms of service**

### Access Control
- **Read-only API access** where possible
- **Principle of least privilege**
- **Regular credential rotation**

## Monitoring and Observability

### Metrics Collection
- **API call counts** and success rates
- **Rate limit utilization**
- **Message processing throughput**
- **Error rates** by type and platform

### Health Checks
- **API connectivity** verification
- **Credential validity** checking
- **Message queue** health monitoring
- **Overall system** status reporting

### Logging
- **Structured logging** with correlation IDs
- **Debug information** for troubleshooting
- **Performance metrics** for optimization
- **Security events** for audit trails

## Troubleshooting

### Common Issues

#### Authentication Failures
```bash
# Check credentials
python -m ingestion.connector_cli health

# Regenerate tokens if expired
# Update .env file with new credentials
```

#### Rate Limit Exceeded
```bash
# Check current usage
python -m ingestion.connector_cli status

# Adjust monitoring frequency
# Use polling mode instead of streaming
```

#### No Results Found
```bash
# Test search functionality
python -m ingestion.connector_cli test-search --platform twitter --query "test"

# Check API permissions
# Verify search terms and filters
```

#### Connection Timeouts
```bash
# Check network connectivity
# Verify API endpoints are accessible
# Review firewall settings
```

### Debug Mode
Enable debug logging for detailed troubleshooting:

```python
import logging
logging.getLogger('ingestion').setLevel(logging.DEBUG)
```

## Best Practices

### 1. Credential Management
- Use environment variables for all credentials
- Rotate API keys regularly
- Monitor for credential expiration
- Use separate credentials for development/production

### 2. Rate Limit Management
- Monitor usage patterns
- Implement backoff strategies
- Use appropriate monitoring modes
- Cache results when possible

### 3. Error Handling
- Implement comprehensive error handling
- Log errors with sufficient context
- Use circuit breakers for external dependencies
- Gracefully handle partial failures

### 4. Performance
- Use async/await for I/O operations
- Implement connection pooling
- Monitor memory usage
- Optimize batch sizes

### 5. Security
- Follow platform terms of service
- Implement proper access controls
- Monitor for suspicious activity
- Regular security audits

## Testing

### Unit Tests
```bash
# Run connector tests
python -m ingestion.test_connectors

# Test specific functionality
python -m pytest ingestion/test_connectors.py::test_search_functionality
```

### Integration Tests
```bash
# Test with real APIs (requires credentials)
python -m ingestion.connector_cli test-search --platform twitter --query "test"
```

### Load Testing
```bash
# Test high-volume scenarios
python -m ingestion.test_connectors --load-test --duration 300
```

## Future Enhancements

### Additional Platforms
- **TikTok API** integration
- **Reddit API** connector
- **YouTube API** monitoring
- **Telegram Bot API** integration

### Advanced Features
- **Machine learning** for content classification
- **Image analysis** for visual threats
- **Sentiment analysis** integration
- **Network analysis** for coordinated behavior

### Performance Improvements
- **Distributed processing** across multiple workers
- **Advanced caching** strategies
- **Real-time analytics** dashboards
- **Predictive rate limiting**