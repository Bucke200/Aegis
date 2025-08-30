# Aegis Web Scraping System

The Aegis platform includes comprehensive web scraping capabilities for monitoring threats across various websites and platforms. The scraping system focuses on detecting leaked information, exposed credentials, and threat-related content.

## Supported Sources

### 1. Pastebin Scraper
- **Archive monitoring** for recent public pastes
- **Trending content** analysis
- **Credential detection** with pattern matching
- **Threat analysis** for leaked information
- **Respectful rate limiting** (1 request per 2 seconds)

### 2. GitHub Scraper
- **Repository search** across public repositories
- **Code file analysis** for exposed secrets
- **Issue monitoring** for security discussions
- **API integration** with optional token authentication
- **Security analysis** for hardcoded credentials

## Architecture

### Base Scraper Class
All scrapers inherit from `BaseScraper` which provides:

- **Rate limiting** with configurable limits
- **Error handling** and retry logic
- **Content parsing** with BeautifulSoup
- **Message processing** and publishing
- **Health monitoring** and metrics
- **Async/await** support for high performance

### Scraper Manager
The `WebScraperManager` coordinates multiple scrapers:

- **Multi-source scraping** with unified interface
- **Task management** for scraping campaigns
- **Load balancing** across scrapers
- **Centralized configuration** and monitoring

## Configuration

### Environment Variables

```bash
# GitHub API (optional - improves rate limits)
GITHUB_TOKEN=your_github_personal_access_token

# Scraping Configuration
SCRAPING_USER_AGENT=Aegis-ThreatMonitor/1.0 (Security Research)
SCRAPING_REQUEST_DELAY=2.0
SCRAPING_MAX_RETRIES=3

# Rate Limiting
PASTEBIN_REQUESTS_PER_MINUTE=20
PASTEBIN_REQUESTS_PER_HOUR=500
GITHUB_REQUESTS_PER_MINUTE=30
GITHUB_REQUESTS_PER_HOUR=1000
```

### Rate Limiting Configuration

#### Pastebin
- **0.5 requests per second** (1 request every 2 seconds)
- **20 requests per minute**
- **500 requests per hour**
- **Respectful crawling** practices

#### GitHub
- **0.5 requests per second** for web scraping
- **30 requests per minute**
- **1000 requests per hour**
- **Higher limits** with API token authentication

## Usage Examples

### Basic Scraper Usage

```python
from scraping.pastebin_scraper import create_pastebin_scraper
from scraping.github_scraper import create_github_scraper

# Initialize scrapers
pastebin = create_pastebin_scraper()
github = create_github_scraper()

# Start scrapers
await pastebin.start()
await github.start()

# Search for content
async for content in pastebin.search_content("celebrity leak", limit=20):
    print(f"Found: {content['title']}")
    if content.get('threat_analysis', {}).get('threat_score', 0) > 0.5:
        print("⚠️ High threat score detected!")

# Scrape specific URL
content_data = await github.scrape_url("https://github.com/user/repo/blob/main/config.py")
if content_data and content_data.get('security_analysis', {}).get('has_api_keys'):
    print("🔒 API keys detected in code!")
```

### Scraper Manager Usage

```python
from scraping.scraper_manager import scraper_manager, ScrapingMode
from messaging.schemas import SourceType

# Initialize all available scrapers
await scraper_manager.initialize()

# Start scraping task
await scraper_manager.start_scraping(
    task_id="vip_monitoring",
    keywords=["celebrity_name", "leak", "hack", "credentials"],
    vips=["celebrity_name", "public_figure"],
    sources=[SourceType.PASTEBIN, SourceType.GITHUB],
    mode=ScrapingMode.HYBRID,
    interval=600  # 10 minutes
)

# Check status
status = scraper_manager.get_status()
print(f"Active scrapers: {status['active_scrapers']}")
print(f"Active tasks: {status['active_tasks']}")

# Stop scraping
await scraper_manager.stop_scraping("vip_monitoring")
```

### Direct URL Scraping

```python
# Scrape specific URLs directly
pastebin_content = await scraper_manager.scrape_url_direct(
    "https://pastebin.com/AbCdEfGh"
)

github_content = await scraper_manager.scrape_url_direct(
    "https://github.com/user/repo/blob/main/secrets.py"
)
```

## CLI Management

### Initialize Scrapers

```bash
# Initialize all available scrapers
make scrapers-init

# Initialize specific sources
python -m scraping.scraper_cli init --sources pastebin,github
```

### Monitor Status

```bash
# Check scraper status
make scrapers-status

# Check scraper health
make scrapers-health
```

### Start Scraping

```bash
# Start scraping task
python -m scraping.scraper_cli start-scraping \
    --task-id "threat_monitoring" \
    --keywords "celebrity_name,leak,hack" \
    --vips "celebrity_name" \
    --sources "pastebin,github" \
    --mode "hybrid" \
    --interval 600
```

### Test Functionality

```bash
# Test search functionality
python -m scraping.scraper_cli test-search \
    --source pastebin \
    --query "password leak"

# Scrape specific URL
python -m scraping.scraper_cli scrape-url \
    --url "https://pastebin.com/example"
```

### Configuration Template

```bash
# Generate configuration template
python -m scraping.scraper_cli config-template --output .env.scraping
```

## Scraping Modes

### 1. Search Only (`search_only`)
- **Periodic searches** for keywords and VIPs
- **Historical content** access
- **Lower resource usage**
- **Best for**: Research, historical analysis

### 2. Monitor Only (`monitor_only`)
- **Continuous monitoring** with scraper-specific methods
- **Real-time detection** of new content
- **Higher resource usage**
- **Best for**: Active threat monitoring

### 3. Hybrid (`hybrid`)
- **Combines search and monitoring**
- **Comprehensive coverage**
- **Balanced resource usage**
- **Best for**: Complete threat detection

## Content Analysis

### Threat Detection (Pastebin)
The Pastebin scraper includes advanced threat detection:

```python
threat_patterns = [
    r'\b(?:password|pass|pwd)\s*[:=]\s*\S+',
    r'\b(?:email|mail)\s*[:=]\s*\S+@\S+',
    r'\b(?:api[_\s]?key|token|secret)\s*[:=]\s*\S+',
    r'\b(?:credit|card|cc)\s*[:=]\s*\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}',
    r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----'
]
```

**Threat Analysis Results:**
```python
{
    'has_credentials': True,
    'has_personal_info': True,
    'has_financial_info': False,
    'has_api_keys': True,
    'threat_score': 0.85,
    'detected_patterns': [
        {
            'pattern': 'password',
            'count': 3,
            'samples': ['password = "secret123"', ...]
        }
    ]
}
```

### Security Analysis (GitHub)
The GitHub scraper includes security analysis for code:

```python
security_patterns = [
    r'(?i)\b(?:password|pass|pwd)\s*[:=]\s*["\']?[^"\'\s]+["\']?',
    r'(?i)\b(?:api[_\s]?key|apikey)\s*[:=]\s*["\']?[^"\'\s]+["\']?',
    r'(?i)-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----',
    r'(?i)\b(?:aws[_\s]?(?:access[_\s]?)?key|aws[_\s]?secret)\s*[:=]\s*["\']?[^"\'\s]+["\']?'
]
```

**Security Analysis Results:**
```python
{
    'has_credentials': True,
    'has_api_keys': True,
    'has_private_keys': False,
    'has_database_urls': True,
    'security_score': 0.92,
    'detected_issues': [
        {
            'type': 'api_key',
            'count': 2,
            'samples': ['API_KEY = "sk-abc123"', ...]
        }
    ]
}
```

## Message Processing

### Standardized Format
All scrapers produce messages in standardized format:

```python
{
    "url": "https://source.com/content",
    "title": "Content Title",
    "content": "Full content text",
    "author": "content_author",
    "published_at": "2024-01-01T12:00:00Z",
    "scraped_at": "2024-01-01T12:05:00Z",
    "word_count": 150,
    "line_count": 10,
    "language": "python",
    "page_hash": "sha256_hash_of_content",
    "threat_analysis": { /* threat detection results */ },
    "security_analysis": { /* security analysis results */ }
}
```

### Message Routing
Messages are automatically routed through the message queue system:

- **Exchange**: `threat_data`
- **Routing Key**: `scraping.{source}` (e.g., `scraping.pastebin`)
- **Priority**: Based on threat/security scores and VIP involvement
- **Enrichment**: Automatic metadata addition

## Rate Limiting and Ethics

### Respectful Crawling
- **Reasonable delays** between requests
- **Robots.txt compliance** where applicable
- **User-Agent identification** for transparency
- **Rate limit respect** to avoid overloading servers

### Rate Limit Implementation
```python
class RateLimitConfig:
    requests_per_second: float = 0.5
    requests_per_minute: int = 20
    requests_per_hour: int = 500
    delay_between_requests: float = 2.0
    backoff_factor: float = 2.0
    max_delay: float = 60.0
```

### Automatic Backoff
- **Exponential backoff** on rate limit hits
- **Automatic retry** with increasing delays
- **Circuit breaker** for persistent failures
- **Graceful degradation** when limits reached

## Error Handling

### Connection Errors
- **Automatic retry** with exponential backoff
- **Timeout handling** for slow responses
- **Network error recovery**
- **Graceful failure** handling

### Parsing Errors
- **Robust HTML parsing** with fallback methods
- **Content extraction** error handling
- **Invalid data** graceful processing
- **Partial failure** recovery

### Rate Limit Handling
- **429 status code** detection and handling
- **Retry-After header** respect
- **Automatic waiting** with backoff
- **Status monitoring** during rate limits

## Performance Optimization

### Async Processing
- **Non-blocking I/O** for all HTTP requests
- **Concurrent scraping** across multiple sources
- **Efficient memory usage** with generators
- **Connection pooling** for better performance

### Content Deduplication
- **SHA-256 hashing** of content for deduplication
- **URL normalization** to prevent duplicate scraping
- **Content fingerprinting** for similar content detection

### Caching
- **Request caching** to avoid duplicate requests
- **Content caching** for recently scraped pages
- **Rate limit info** caching
- **DNS resolution** caching

## Security Considerations

### Data Privacy
- **Minimal data collection** - only what's needed for threat detection
- **No storage of personal information** beyond analysis
- **Secure transmission** of scraped data
- **Compliance with privacy regulations**

### Access Control
- **Read-only access** to public content only
- **No authentication bypass** attempts
- **Respect for access controls** and privacy settings
- **Terms of service** compliance

### Content Handling
- **Secure content processing** to prevent injection attacks
- **Sanitization** of scraped content before processing
- **Safe parsing** of HTML and other formats
- **Malware detection** for downloaded content

## Monitoring and Observability

### Metrics Collection
- **Scraping throughput** and success rates
- **Rate limit utilization** and hits
- **Content analysis** statistics
- **Error rates** by type and source

### Health Checks
- **Site accessibility** verification
- **Scraper functionality** testing
- **Content parsing** validation
- **Message queue** connectivity

### Logging
- **Structured logging** with correlation IDs
- **Debug information** for troubleshooting
- **Performance metrics** for optimization
- **Security events** for audit trails

## Troubleshooting

### Common Issues

#### Site Accessibility
```bash
# Test site connectivity
python -m scraping.scraper_cli health

# Check specific source
curl -I https://pastebin.com
curl -I https://github.com
```

#### Rate Limiting
```bash
# Check current usage
python -m scraping.scraper_cli status

# Adjust scraping frequency
# Reduce interval in scraping tasks
# Use search_only mode instead of hybrid
```

#### No Results Found
```bash
# Test search functionality
python -m scraping.scraper_cli test-search --source pastebin --query "test"

# Check search terms and filters
# Verify site structure hasn't changed
```

#### Parsing Errors
```bash
# Test specific URL scraping
python -m scraping.scraper_cli scrape-url --url "https://pastebin.com/example"

# Check HTML structure changes
# Review parsing logic for updates needed
```

### Debug Mode
Enable debug logging for detailed troubleshooting:

```python
import logging
logging.getLogger('scraping').setLevel(logging.DEBUG)
```

## Best Practices

### 1. Ethical Scraping
- Always respect robots.txt files
- Use reasonable delays between requests
- Identify your scraper with proper User-Agent
- Comply with terms of service
- Don't overload target servers

### 2. Rate Limit Management
- Monitor usage patterns and adjust accordingly
- Implement proper backoff strategies
- Use caching to reduce redundant requests
- Respect server-indicated rate limits

### 3. Error Handling
- Implement comprehensive error handling
- Log errors with sufficient context
- Use circuit breakers for external dependencies
- Gracefully handle partial failures

### 4. Performance
- Use async/await for I/O operations
- Implement connection pooling
- Monitor memory usage
- Optimize parsing logic

### 5. Security
- Sanitize all scraped content
- Implement proper access controls
- Monitor for suspicious patterns
- Regular security audits

## Testing

### Unit Tests
```bash
# Run scraper tests
python -m scraping.test_scrapers

# Test specific functionality
python -m pytest scraping/test_scrapers.py::test_threat_detection
```

### Integration Tests
```bash
# Test with real sites (requires network access)
python -m scraping.scraper_cli test-search --source pastebin --query "test"
```

### Load Testing
```bash
# Test high-volume scenarios
python -m scraping.test_scrapers --load-test --duration 300
```

## Future Enhancements

### Additional Sources
- **Reddit API** integration for forum monitoring
- **Discord** public server scraping
- **Telegram** public channel monitoring
- **Dark web** monitoring capabilities

### Advanced Features
- **Machine learning** for content classification
- **Natural language processing** for threat detection
- **Image analysis** for visual content
- **Network analysis** for coordinated campaigns

### Performance Improvements
- **Distributed scraping** across multiple workers
- **Advanced caching** strategies
- **Real-time processing** pipelines
- **Predictive rate limiting**