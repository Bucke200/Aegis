# Aegis Platform Makefile

.PHONY: help install dev test clean docker-up docker-down migrate

help:
	@echo "Aegis VIP Threat Monitoring Platform"
	@echo "===================================="
	@echo ""
	@echo "🚀 Quick Start:"
	@echo "  python start.py              - Automated setup (recommended)"
	@echo "  make setup                   - Manual platform setup"
	@echo "  make monitor VIP=\"Name\"      - Start monitoring a VIP"
	@echo "  make status                  - Show system status"
	@echo "  make test-twitter            - Test Twitter connection"
	@echo ""
	@echo "📖 Examples:"
	@echo "  make monitor VIP=\"Elon Musk\""
	@echo "  python main.py monitor --vip \"Celebrity Name\" --keywords \"scam,hack\""
	@echo ""
	@echo "🔧 Development:"
	@echo "  install     - Install Python dependencies"
	@echo "  dev         - Start development environment"
	@echo "  test        - Run tests"
	@echo "  clean       - Clean up temporary files"
	@echo ""
	@echo "🐳 Infrastructure:"
	@echo "  docker-up   - Start Docker services"
	@echo "  docker-down - Stop Docker services"
	@echo "  migrate     - Run database migrations"
	@echo ""
	@echo "📨 Message Queue:"
	@echo "  queue-setup - Setup message queue infrastructure"
	@echo "  queue-health - Check message queue health"
	@echo "  queue-stats - Show queue statistics"
	@echo "  queue-monitor - Monitor queue activity"
	@echo ""
	@echo "🔗 Connectors:"
	@echo "  connectors-init - Initialize social media connectors"
	@echo "  connectors-status - Show connector status"
	@echo "  connectors-health - Check connector health"
	@echo ""
	@echo "🕷️ Scrapers:"
	@echo "  scrapers-init - Initialize web scrapers"
	@echo "  scrapers-status - Show scraper status"
	@echo "  scrapers-health - Check scraper health"
	@echo ""
	@echo "📋 Format System:"
	@echo "  format-test - Test message format system"
	@echo "  format-schemas - Show message schemas"
	@echo "  format-routing - Show routing configuration"
	@echo ""
	@echo "🛠️ Utilities:"
	@echo "  lint        - Run code linting"
	@echo "  format      - Format code with black"

install:
	pip install -r requirements.txt
	cd frontend && npm install

dev: docker-up
	@echo "Starting development servers..."
	@echo "API will be available at http://localhost:8000"
	@echo "Frontend will be available at http://localhost:3000"
	python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000 &
	cd frontend && npm start

test:
	pytest tests/ -v

clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build/
	rm -rf dist/

docker-up:
	docker-compose up -d
	@echo "Waiting for services to start..."
	sleep 10

docker-down:
	docker-compose down

migrate:
	cd storage && alembic upgrade head

lint:
	flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
	mypy . --ignore-missing-imports

format:
	black . --line-length 88
	isort . --profile black

queue-setup:
	python -m messaging.queue_cli setup

queue-health:
	python -m messaging.queue_cli health

queue-stats:
	python -m messaging.queue_cli stats

queue-monitor:
	python -m messaging.queue_cli monitor

format-test:
	python -m messaging.format_cli test

format-schemas:
	python -m messaging.format_cli schemas

format-routing:
	python -m messaging.format_cli routing

connectors-init:
	python -m ingestion.connector_cli init

connectors-status:
	python -m ingestion.connector_cli status

connectors-health:
	python -m ingestion.connector_cli health

scrapers-init:
	python -m scraping.scraper_cli init

scrapers-status:
	python -m scraping.scraper_cli status

scrapers-health:
	python -m scraping.scraper_cli health

# Main application commands
setup: install docker-up migrate queue-setup
	@echo "🚀 Setting up Aegis platform..."
	python main.py setup
	@echo ""
	@echo "✅ Aegis platform setup complete!"
	@echo ""
	@echo "📝 Next steps:"
	@echo "1. Copy .env.template to .env and add your Twitter Bearer Token"
	@echo "2. Run 'make test-twitter' to verify Twitter connection"
	@echo "3. Run 'make monitor VIP=\"Celebrity Name\"' to start monitoring"

monitor:
	@if [ -z "$(VIP)" ]; then \
		echo "❌ Please specify a VIP name: make monitor VIP=\"Celebrity Name\""; \
	else \
		echo "🔍 Starting monitoring for: $(VIP)"; \
		python main.py monitor --vip "$(VIP)"; \
	fi

status:
	python main.py status

test-twitter:
	python main.py test

config:
	python main.py config