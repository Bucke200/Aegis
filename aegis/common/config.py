"""Application settings, loaded from environment variables and `.env`."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Aegis runtime configuration.

    Every field is overridable with an ``AEGIS_``-prefixed environment
    variable, for example ``AEGIS_DATABASE_URL``.
    """

    model_config = SettingsConfigDict(
        env_prefix="AEGIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: str = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://aegis:aegis123@localhost:5432/aegis"
    rabbitmq_url: str = "amqp://aegis:aegis123@localhost:5672/"

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "aegis"
    minio_secret_key: SecretStr = SecretStr("aegis123")
    minio_secure: bool = False
    minio_evidence_bucket: str = "aegis-evidence"
    minio_media_bucket: str = "aegis-media"
    minio_retention_access_key: str = ""
    minio_retention_secret_key: SecretStr = SecretStr("")

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    jwt_secret: SecretStr = SecretStr("change-me")
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    refresh_cookie_name: str = "aegis_refresh"
    refresh_cookie_secure: bool = False
    refresh_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cors_origins: str = "http://localhost:5173,http://localhost:4173"
    rate_limit_per_minute: int = 120
    event_consumer_enabled: bool = True

    app_encryption_key: SecretStr = SecretStr("change-me")

    fingerprint_salt_id: str = "default"
    fingerprint_salt: SecretStr = SecretStr("change-me")
    fingerprint_previous_salts: str = ""

    llm_provider: str = ""
    llm_model: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_daily_token_budget: int = 1_000_000
    llm_base_url: str = "https://api.openai.com/v1"
    llm_timeout_seconds: float = 30.0
    llm_reserved_tokens_per_call: int = 1500

    stage1_threshold: float = 0.35
    toxicity_enabled: bool = True
    toxicity_model: str = "unitary/multilingual-toxic-xlm-roberta"

    telegram_api_id: int | None = None
    telegram_api_hash: SecretStr | None = None
    telegram_session: str = ""

    github_token: SecretStr | None = None

    clamav_host: str = "clamav"
    clamav_port: int = 3310

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = ""

    slack_bot_token: SecretStr = SecretStr("")
    slack_signing_secret: SecretStr = SecretStr("")
    slack_webhook_url: str = ""

    capture_egress_proxy: str = ""

    @field_validator("telegram_api_id", mode="before")
    @classmethod
    def _empty_string_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator("database_url", "rabbitmq_url")
    @classmethod
    def _require_scheme(cls, value: str) -> str:
        if "://" not in value:
            raise ValueError("must be a URL with a scheme")
        return value

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


DEFAULT_SECRET_VALUES: dict[str, str] = {
    "jwt_secret": "change-me",
    "app_encryption_key": "change-me",
    "fingerprint_salt": "change-me",
    "minio_secret_key": "aegis123",
}


def check_insecure_defaults(settings: Settings) -> list[str]:
    """Return the names of secret settings still set to their default value."""

    insecure: list[str] = []
    for field, default in DEFAULT_SECRET_VALUES.items():
        value = getattr(settings, field)
        raw = value.get_secret_value() if isinstance(value, SecretStr) else str(value)
        if raw == default:
            insecure.append(field)
    return insecure


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    return Settings()
