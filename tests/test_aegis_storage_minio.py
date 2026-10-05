"""MinIO integration tests.

These run only when AEGIS_TEST_MINIO_ENDPOINT and the app/retention credentials
are set to a disposable MinIO instance (see the CI provisioning step).
"""

from __future__ import annotations

import os
import uuid

import pytest
from minio.error import S3Error

from aegis.common.config import Settings
from aegis.common.storage import ObjectStorage, evidence_object_key, sha256_hex

pytestmark = pytest.mark.skipif(
    not os.environ.get("AEGIS_TEST_MINIO_ENDPOINT"),
    reason="AEGIS_TEST_MINIO_ENDPOINT is not set",
)


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        minio_endpoint=os.environ["AEGIS_TEST_MINIO_ENDPOINT"],
        minio_access_key=os.environ["AEGIS_TEST_MINIO_ACCESS_KEY"],
        minio_secret_key=os.environ["AEGIS_TEST_MINIO_SECRET_KEY"],
        minio_evidence_bucket=os.environ.get("AEGIS_TEST_MINIO_EVIDENCE_BUCKET", "aegis-evidence"),
        minio_media_bucket=os.environ.get("AEGIS_TEST_MINIO_MEDIA_BUCKET", "aegis-media"),
        minio_retention_access_key=os.environ["AEGIS_TEST_MINIO_RETENTION_ACCESS_KEY"],
        minio_retention_secret_key=os.environ["AEGIS_TEST_MINIO_RETENTION_SECRET_KEY"],
        minio_secure=False,
    )


def test_upload_download_and_hash() -> None:
    settings = _settings()
    storage = ObjectStorage.from_settings(settings)
    storage.ensure_buckets()

    key = f"tests/{uuid.uuid4().hex}.bin"
    stored = storage.put_bytes(settings.minio_media_bucket, key, b"payload")

    assert stored.sha256 == sha256_hex(b"payload")
    assert storage.get_bytes(settings.minio_media_bucket, key) == b"payload"
    assert storage.presigned_get_url(settings.minio_media_bucket, key).startswith("http")

    storage.delete(settings.minio_media_bucket, key)
    assert storage.object_exists(settings.minio_media_bucket, key) is False


def test_locked_evidence_needs_the_retention_role() -> None:
    settings = _settings()
    storage = ObjectStorage.from_settings(settings)
    storage.ensure_buckets()

    key = evidence_object_key(uuid.uuid4(), "screenshot", uuid.uuid4().hex)
    storage.put_bytes(settings.minio_evidence_bucket, key, b"evidence", retention_days=1)

    version_id = storage.client.stat_object(settings.minio_evidence_bucket, key).version_id
    assert version_id

    with pytest.raises(S3Error):
        storage.delete(settings.minio_evidence_bucket, key, version_id=version_id)

    retention_storage = storage.with_retention_credentials(settings)
    retention_storage.delete(
        settings.minio_evidence_bucket,
        key,
        version_id=version_id,
        bypass_governance=True,
    )
    assert storage.object_exists(settings.minio_evidence_bucket, key) is False
