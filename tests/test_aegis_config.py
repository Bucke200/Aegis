"""Smoke tests for application settings."""

from __future__ import annotations

from aegis.common.config import Settings, check_insecure_defaults, get_settings


def test_defaults_load() -> None:
    settings = Settings(_env_file=None, environment="development")
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.api_port == 8000
    assert settings.minio_media_bucket == "aegis-media"


def test_environment_override(monkeypatch) -> None:
    monkeypatch.setenv("AEGIS_API_PORT", "9100")
    settings = Settings(_env_file=None)
    assert settings.api_port == 9100


def test_empty_telegram_api_id_becomes_none(monkeypatch) -> None:
    monkeypatch.setenv("AEGIS_TELEGRAM_API_ID", "")
    settings = Settings(_env_file=None)
    assert settings.telegram_api_id is None


def test_insecure_defaults_detected(monkeypatch) -> None:
    for variable in ("AEGIS_JWT_SECRET", "AEGIS_APP_ENCRYPTION_KEY", "AEGIS_MINIO_SECRET_KEY"):
        monkeypatch.delenv(variable, raising=False)
    settings = Settings(_env_file=None)
    insecure = check_insecure_defaults(settings)
    assert "jwt_secret" in insecure
    assert "app_encryption_key" in insecure
    assert "minio_secret_key" in insecure


def test_insecure_defaults_cleared(monkeypatch) -> None:
    monkeypatch.setenv("AEGIS_JWT_SECRET", "a-strong-secret")
    monkeypatch.setenv("AEGIS_APP_ENCRYPTION_KEY", "another-strong-secret")
    monkeypatch.setenv("AEGIS_MINIO_SECRET_KEY", "not-the-default")
    settings = Settings(_env_file=None)
    assert check_insecure_defaults(settings) == []


def test_get_settings_is_cached() -> None:
    get_settings.cache_clear()
    assert get_settings() is get_settings()
    get_settings.cache_clear()
