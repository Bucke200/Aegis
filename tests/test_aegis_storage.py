"""Unit tests for the MinIO storage wrapper."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import Mock

import pytest
from minio import Minio
from minio.commonconfig import ENABLED, GOVERNANCE

from aegis.common.config import Settings
from aegis.common.storage import (
    ObjectStorage,
    evidence_object_key,
    media_object_key,
    sha256_hex,
)

ABC_SHA256 = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def make_storage(client: Mock) -> ObjectStorage:
    return ObjectStorage(cast(Minio, client), "aegis-evidence", "aegis-media")


def test_sha256_hex_matches_known_vector() -> None:
    assert sha256_hex(b"abc") == ABC_SHA256


def test_object_key_builders() -> None:
    incident_id = uuid.uuid4()
    assert evidence_object_key(incident_id, "screenshot", ABC_SHA256) == (
        f"evidence/{incident_id}/screenshot/{ABC_SHA256}"
    )
    assert media_object_key(ABC_SHA256) == f"media/{ABC_SHA256}"


def test_put_bytes_returns_hash_and_size() -> None:
    client = Mock(spec=Minio)
    storage = make_storage(client)

    stored = storage.put_bytes("aegis-media", "media/x", b"abc", content_type="text/plain")

    assert stored.sha256 == ABC_SHA256
    assert stored.size == 3
    assert stored.bucket == "aegis-media"
    _, kwargs = client.put_object.call_args
    assert kwargs["length"] == 3
    assert kwargs["content_type"] == "text/plain"
    assert kwargs["retention"] is None


def test_put_bytes_applies_governance_retention() -> None:
    client = Mock(spec=Minio)
    storage = make_storage(client)

    storage.put_bytes("aegis-evidence", "evidence/x", b"abc", retention_days=365)

    _, kwargs = client.put_object.call_args
    retention = kwargs["retention"]
    assert retention.mode == GOVERNANCE
    assert retention.retain_until_date > datetime.now(tz=UTC)


def test_get_bytes_closes_response() -> None:
    client = Mock(spec=Minio)
    response = Mock()
    response.read.return_value = b"abc"
    client.get_object.return_value = response
    storage = make_storage(client)

    assert storage.get_bytes("aegis-media", "media/x") == b"abc"
    response.close.assert_called_once()
    response.release_conn.assert_called_once()


def test_presigned_url_uses_expiry() -> None:
    client = Mock(spec=Minio)
    client.presigned_get_object.return_value = "https://example.test/signed"
    storage = make_storage(client)

    url = storage.presigned_get_url("aegis-media", "media/x", expires=timedelta(minutes=5))

    assert url == "https://example.test/signed"
    _, kwargs = client.presigned_get_object.call_args
    assert kwargs["expires"] == timedelta(minutes=5)


def test_delete_without_bypass_uses_remove_object() -> None:
    client = Mock(spec=Minio)
    storage = make_storage(client)

    storage.delete("aegis-media", "media/x")

    client.remove_object.assert_called_once_with("aegis-media", "media/x", version_id=None)
    client.remove_objects.assert_not_called()


def test_delete_specific_version() -> None:
    client = Mock(spec=Minio)
    storage = make_storage(client)

    storage.delete("aegis-evidence", "evidence/x", version_id="v1")

    client.remove_object.assert_called_once_with("aegis-evidence", "evidence/x", version_id="v1")


def test_delete_with_bypass_uses_batch_api() -> None:
    client = Mock(spec=Minio)
    storage = make_storage(client)

    storage.delete("aegis-evidence", "evidence/x", bypass_governance=True)

    client.remove_object.assert_not_called()
    _, kwargs = client.remove_objects.call_args
    assert kwargs["bypass_governance_mode"] is True


def test_set_governance_retention() -> None:
    client = Mock(spec=Minio)
    storage = make_storage(client)
    retain_until = datetime.now(tz=UTC) + timedelta(days=30)

    storage.set_governance_retention("aegis-evidence", "evidence/x", retain_until)

    _, _, config = client.set_object_retention.call_args.args
    assert config.mode == GOVERNANCE
    assert config.retain_until_date == retain_until


def test_ensure_buckets_creates_locked_evidence_and_versioned_media() -> None:
    client = Mock(spec=Minio)
    client.bucket_exists.return_value = False
    storage = make_storage(client)

    storage.ensure_buckets()

    client.make_bucket.assert_any_call("aegis-evidence", object_lock=True)
    client.make_bucket.assert_any_call("aegis-media")
    _, versioning = client.set_bucket_versioning.call_args.args
    assert versioning.status == ENABLED


def test_object_exists_returns_false_on_error() -> None:
    client = Mock(spec=Minio)
    client.stat_object.side_effect = RuntimeError("missing")
    storage = make_storage(client)
    assert storage.object_exists("aegis-media", "media/x") is False


def test_retention_client_requires_credentials() -> None:
    settings = Settings(_env_file=None, minio_retention_access_key="", minio_retention_secret_key="")
    with pytest.raises(ValueError, match="retention credentials"):
        ObjectStorage.from_settings(settings).retention_client(settings)


def test_retention_client_is_a_minio_client() -> None:
    settings = Settings(
        _env_file=None,
        minio_endpoint="localhost:9000",
        minio_retention_access_key="retention",
        minio_retention_secret_key="secret",
    )
    client = ObjectStorage.from_settings(settings).retention_client(settings)
    assert isinstance(client, Minio)
