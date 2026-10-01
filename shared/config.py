"""
Shared configuration management for Aegis platform
"""
import os
from typing import List, Optional
from pydantic_settings import BaseSettings

INSECURE_DEFAULTS = {
    "secret_key": "your-secret-key-change-in-production",
    "database_url": "postgresql://aegis:aegis123@localhost:5432/aegis",
    "rabbitmq_url": "amqp://aegis:aegis123@localhost:5672/",
    "rabbitmq_password": "aegis123",
}


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Database
    database_url: str = "postgresql://aegis:aegis123@localhost:5432/aegis"
    
    # Message Queue
    rabbitmq_url: str = "amqp://aegis:aegis123@localhost:5672/"
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "aegis"
    rabbitmq_password: str = "aegis123"
    rabbitmq_vhost: str = "/"
    
    # Search Engine
    elasticsearch_url: str = "http://localhost:9200"
    
    # Cache
    redis_url: str = "redis://localhost:6379"
    
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    secret_key: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    
    # Social Media APIs
    # Twitter/X API
    twitter_api_key: Optional[str] = None
    twitter_api_secret: Optional[str] = None
    twitter_access_token: Optional[str] = None
    twitter_access_token_secret: Optional[str] = None
    twitter_bearer_token: Optional[str] = None
    twitter_client_id: Optional[str] = None
    twitter_client_secret: Optional[str] = None
    
    # Meta (Facebook/Instagram) API
    facebook_access_token: Optional[str] = None
    facebook_app_id: Optional[str] = None
    facebook_app_secret: Optional[str] = None
    instagram_business_account_id: Optional[str] = None
    
    # LinkedIn API
    linkedin_access_token: Optional[str] = None
    linkedin_organization_id: Optional[str] = None
    linkedin_client_id: Optional[str] = None
    linkedin_client_secret: Optional[str] = None
    
    # Messaging Platform Bots
    telegram_bot_token: Optional[str] = None
    discord_bot_token: Optional[str] = None
    
    # External Services
    google_lens_api_key: Optional[str] = None
    
    # Web Scraping
    github_token: Optional[str] = None
    scraping_user_agent: str = "Aegis-ThreatMonitor/1.0 (Security Research)"
    scraping_request_delay: float = 2.0
    scraping_max_retries: int = 3
    
    # File Storage
    storage_path: str = "./storage/files"
    max_file_size: str = "50MB"
    
    # Logging
    log_level: str = "INFO"
    log_file: str = "./logs/aegis.log"
    
    class Config:
        env_file = ".env"
        case_sensitive = False

    def check_insecure_defaults(self) -> List[str]:
        """Return names of settings still using insecure development defaults"""
        return [
            name for name, default in INSECURE_DEFAULTS.items()
            if getattr(self, name, None) == default
        ]


# Global settings instance
settings = Settings()