# Aegis VIP Threat Monitoring Platform

A comprehensive threat monitoring system designed to protect VIPs and public figures from online threats, impersonation, and coordinated attacks across social media platforms.

## 🚀 Quick Start

### Prerequisites

- Python 3.10–3.12
- [uv](https://docs.astral.sh/uv/) (dependency management)
- Docker and Docker Compose
- Twitter Developer Account (for API access)

### Option 1: Automated Setup (Recommended)

```bash
# Clone the repository
git clone <repository-url>
cd aegis-threat-monitor

# Run the automated setup script
python start.py
```

The script will:
1. ✅ Check requirements (Python, uv, Docker)
2. 📦 Install dependencies
3. 🐳 Start infrastructure services
4. 🚀 Setup the platform
5. 📝 Create configuration file
6. 🐦 Test Twitter connection (if configured)

### Option 2: Manual Setup

```bash
# 1. Install dependencies (creates .venv from uv.lock)
uv sync

# 2. Start infrastructure
make docker-up

# 3. Setup platform
make setup

# 4. Configure Twitter API
cp .env.template .env
# Edit .env and add your TWITTER_BEARER_TOKEN

# 5. Test connection
uv run python main.py test
```

### Get Twitter API Access

1. Go to [Twitter Developer Portal](https://developer.twitter.com/)
2. Create a new app
3. Generate a Bearer Token
4. Add it to your `.env` file:

```bash
TWITTER_BEARER_TOKEN=your_bearer_token_here
```

### Start Monitoring

```bash
# Monitor a VIP
python main.py monitor --vip "Elon Musk"

# Monitor with custom keywords
python main.py monitor --vip "Celebrity Name" --keywords "scam,hack,leak,threat"

# Or use Make shortcuts
make monitor VIP="Celebrity Name"
```

## 📊 Usage

### Basic Commands

```bash
# Show system status
python main.py status

# Show configuration template
python main.py config

# Test Twitter connection
python main.py test
```

### Advanced Usage

```bash
# Use Makefile shortcuts
make connectors-init     # Initialize social media connectors
make connectors-status   # Show connector status
make queue-health        # Check message queue health
make format-test         # Test message format system
```

## 🏗️ Architecture

### Core Components

- **Ingestion Layer**: Social media API connectors (Twitter, Facebook, Instagram, LinkedIn)
- **Message Queue**: RabbitMQ for reliable message processing
- **Storage Layer**: PostgreSQL + Elasticsearch for data storage and search
- **Analysis Engine**: NLP and ML-based threat detection
- **Web Scraping**: Pastebin and GitHub monitoring for leaked information

### Message Flow

1. **Data Collection** → Social media APIs and web scraping
2. **Message Processing** → Standardized format and validation
3. **Threat Analysis** → NLP analysis and pattern detection
4. **Alert Generation** → Real-time notifications for threats
5. **Evidence Collection** → Screenshots and media preservation

## 🔧 Configuration

### Environment Variables

```bash
# Twitter API (Required for basic functionality)
TWITTER_BEARER_TOKEN=your_bearer_token

# Database
DATABASE_URL=postgresql://aegis:aegis123@localhost:5432/aegis

# Message Queue
RABBITMQ_URL=amqp://aegis:aegis123@localhost:5672/

# Search Engine
ELASTICSEARCH_URL=http://localhost:9200

# Optional: Additional API credentials
FACEBOOK_ACCESS_TOKEN=your_facebook_token
LINKEDIN_ACCESS_TOKEN=your_linkedin_token
GITHUB_TOKEN=your_github_token
```

### Docker Services

The platform uses Docker Compose for infrastructure:

- **PostgreSQL** (port 5432): Primary database
- **RabbitMQ** (port 5672, management 15672): Message queue
- **Elasticsearch** (port 9200): Search and analytics
- **Redis** (port 6379): Caching

All services are defined in `docker-compose.yml` and started with `make docker-up`.

## 🛡️ Features

### Current Features (v1.0)

- ✅ **Twitter Monitoring**: Real-time streaming and search
- ✅ **Message Queue System**: Reliable message processing
- ✅ **Threat Detection**: Basic NLP-based analysis
- ✅ **Web Scraping**: Pastebin and GitHub monitoring
- ✅ **Data Storage**: PostgreSQL and Elasticsearch integration

### Planned Features

- 🔄 **Advanced NLP**: Machine learning threat classification
- 🔄 **Image Analysis**: Deepfake and manipulation detection
- 🔄 **Multi-platform**: Facebook, Instagram, LinkedIn integration
- 🔄 **Web Dashboard**: Real-time monitoring interface
- 🔄 **Alert System**: Email, SMS, and Slack notifications

## 📈 Monitoring

### System Health

```bash
# Check overall system health
python main.py status

# Check individual components
make connectors-health   # Social media connectors
make queue-health       # Message queue system
make scrapers-health    # Web scrapers
```

### Logs

```bash
# View application logs
tail -f logs/aegis.log

# View Docker service logs
docker-compose logs -f rabbitmq
docker-compose logs -f postgres
docker-compose logs -f elasticsearch
```

## 🧪 Testing

### Unit Tests

```bash
# Install dependencies (includes the dev group)
uv sync

# Run the pytest suite
make test          # or: uv run pytest
```

The pytest suite covers message schemas/routing, configuration safeguards,
database initialization, and the connector manager. Legacy component suites
(message format, connectors, scrapers) can still be run directly:

```bash
make test-suites
```

### Integration Tests

```bash
# Test Twitter API connection
python main.py test

# Test specific connector
python -m ingestion.connector_cli test-search --platform twitter --query "test"

# Test web scraper
python -m scraping.scraper_cli test-search --source pastebin --query "test"
```

## 🔁 CI/CD

Pipelines are defined under `.github/workflows/`:

- **CI** (`ci.yml`): runs on every push and pull request. Lints (flake8 + black),
  runs the pytest suite on Python 3.10–3.12, and validates `docker-compose.yml`.
- **CD** (`cd.yml`): on pushes to `master`/`main` and `v*` tags, builds the
  `Dockerfile` and publishes the image to GitHub Container Registry (GHCR):

  ```bash
  docker pull ghcr.io/<owner>/aegis:latest
  ```

Build locally with:

```bash
docker build -t aegis .
```

## 🔒 Security

### Best Practices

- **API Keys**: Store in environment variables, never in code
- **Rate Limiting**: Respect platform rate limits and terms of service
- **Data Privacy**: Minimal data collection, secure transmission
- **Access Control**: Principle of least privilege

### Compliance

- **GDPR**: Data minimization and privacy by design
- **Platform ToS**: Compliance with social media terms of service
- **Ethical Scraping**: Respectful crawling practices

## 🛠️ Development

### Project Structure

```
aegis-threat-monitor/
├── main.py                 # Main application entry point
├── shared/                 # Shared utilities and configuration
├── messaging/              # Message queue and format system
├── ingestion/              # Social media API connectors
├── scraping/               # Web scraping components
├── storage/                # Database models and utilities
├── tests/                  # pytest suite
├── scripts/                # Ad-hoc diagnostic and test helpers
├── pyproject.toml          # Project metadata and dependencies
├── uv.lock                 # Locked dependency graph
├── Dockerfile              # Container image (uv-based)
├── docker-compose.yml      # Infrastructure services
└── Makefile               # Development shortcuts
```

### Adding New Connectors

1. Create connector class inheriting from `BaseSocialMediaConnector`
2. Implement required methods: `search_posts`, `get_user_posts`, `stream_real_time`
3. Add factory function and integrate with connector manager
4. Update configuration and CLI tools

### Adding New Scrapers

1. Create scraper class inheriting from `BaseScraper`
2. Implement required methods: `search_content`, `scrape_url`
3. Add threat/security analysis patterns
4. Integrate with scraper manager

## 📚 Documentation

- [Message Format System](messaging/README.md)
- [Social Media Connectors](ingestion/README.md)
- [Web Scraping System](scraping/README.md)
- [API Documentation](docs/api.md) (coming soon)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

### Common Issues

#### Twitter API Issues
```bash
# Check credentials
python main.py config

# Test connection
python main.py test
```

#### Docker Issues
```bash
# Restart services
make docker-down
make docker-up

# Check service status
docker-compose ps
```

#### Database Issues
```bash
# Reset database
make docker-down
docker volume rm aegis_postgres_data
make docker-up
make setup
```

### Getting Help

- Check the logs: `tail -f logs/aegis.log`
- Review configuration: `python main.py config`
- Test components individually using CLI tools
- Check Docker service status: `docker-compose ps`

## 🎯 Roadmap

### Phase 1: Core Platform (Current)
- ✅ Twitter monitoring
- ✅ Message queue system
- ✅ Basic threat detection
- ✅ Web scraping

### Phase 2: Enhanced Detection
- 🔄 Advanced NLP models
- 🔄 Image analysis
- 🔄 Coordinated behavior detection
- 🔄 Multi-platform correlation

### Phase 3: User Interface
- 🔄 Web dashboard
- 🔄 Real-time alerts
- 🔄 Investigation tools
- 🔄 Reporting system

### Phase 4: Enterprise Features
- 🔄 Multi-tenant support
- 🔄 API access
- 🔄 Advanced analytics
- 🔄 Compliance tools