"""
Tests for application configuration handling.
"""

from shared.config import Settings


def test_defaults_are_flagged_as_insecure():
    settings = Settings(_env_file=None)

    insecure = settings.check_insecure_defaults()

    assert "secret_key" in insecure
    assert "database_url" in insecure
    assert "rabbitmq_url" in insecure
    assert "rabbitmq_password" in insecure


def test_overridden_defaults_are_not_flagged():
    settings = Settings(
        _env_file=None,
        secret_key="a-strong-production-secret",
        database_url="postgresql://user:pw@db:5432/aegis",
        rabbitmq_url="amqp://user:pw@rabbit:5672/",
        rabbitmq_password="s3cr3t",
    )

    assert settings.check_insecure_defaults() == []
