"""MinIO object storage wrapper.

Media and evidence share one client; evidence objects are written with a
governance-mode retention period and can only be deleted before it expires
through the separate retention credential.
"""

from __future__ import annotations

import hashlib
import io
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from minio import Minio
from minio.commonconfig import ENABLED, GOVERNANCE
from minio.deleteobjects import DeleteObject
from minio.retention import Retention
from minio.versioningconfig import VersioningConfig

from aegis.common.config import Settings, get_settings

DEFAULT_URL_EXPIRY = timedelta(hours=1)


def sha256_hex(data: bytes) -> str:
    """Return the hex SHA-256 of a payload."""

    return hashlib.sha256(data).hexdigest()


def evidence_object_key(incident_id: uuid.UUID | str, kind: str, sha256: str) -> str:
    """Build an evidence object key: ``evidence/{incident}/{kind}/{sha256}``."""

    return f"evidence/{incident_id}/{kind}/{sha256}"


def media_object_key(content_sha256: str) -> str:
    """Build a media object key: ``media/{sha256}``."""

    return f"media/{content_sha256}"


@dataclass(frozen=True)
class StoredObject:
    bucket: str
    object_key: str
    sha256: str
    size: int


class DeleteFailedError(RuntimeError):
    """Raised when a batch delete reports per-object failures."""


class ObjectStorage:
    """Thin wrapper over a MinIO client with Aegis bucket conventions."""

    def __init__(self, client: Minio, evidence_bucket: str, media_bucket: str) -> None:
        self.client = client
        self.evidence_bucket = evidence_bucket
        self.media_bucket = media_bucket

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> ObjectStorage:
        settings = settings or get_settings()
        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key.get_secret_value(),
            secure=settings.minio_secure,
        )
        return cls(client, settings.minio_evidence_bucket, settings.minio_media_bucket)

    def retention_client(self, settings: Settings | None = None) -> Minio:
        """Return a client using the separate retention credential."""

        settings = settings or get_settings()
        if not settings.minio_retention_access_key or not settings.minio_retention_secret_key:
            raise ValueError("retention credentials are not configured")
        return Minio(
            settings.minio_endpoint,
            access_key=settings.minio_retention_access_key,
            secret_key=settings.minio_retention_secret_key.get_secret_value(),
            secure=settings.minio_secure,
        )

    @classmethod
    def with_retention_credentials(cls, settings: Settings | None = None) -> ObjectStorage:
        """Return storage bound to the retention credential."""

        settings = settings or get_settings()
        client = cls.from_settings(settings).retention_client(settings)
        return cls(client, settings.minio_evidence_bucket, settings.minio_media_bucket)

    def ensure_buckets(self) -> None:
        """Create the evidence bucket with object lock and version media."""

        if not self.client.bucket_exists(self.evidence_bucket):
            self.client.make_bucket(self.evidence_bucket, object_lock=True)
        if not self.client.bucket_exists(self.media_bucket):
            self.client.make_bucket(self.media_bucket)
            self.client.set_bucket_versioning(self.media_bucket, VersioningConfig(ENABLED))

    def put_bytes(
        self,
        bucket: str,
        object_key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        retention_days: int | None = None,
    ) -> StoredObject:
        """Upload bytes, computing and returning their SHA-256."""

        retention = None
        if retention_days is not None:
            retain_until = datetime.now(tz=UTC) + timedelta(days=retention_days)
            retention = Retention(GOVERNANCE, retain_until)

        self.client.put_object(
            bucket,
            object_key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
            retention=retention,
        )
        return StoredObject(
            bucket=bucket,
            object_key=object_key,
            sha256=sha256_hex(data),
            size=len(data),
        )

    def get_bytes(self, bucket: str, object_key: str) -> bytes:
        """Download an object's full contents."""

        response = self.client.get_object(bucket, object_key)
        try:
            return bytes(response.read())
        finally:
            response.close()
            response.release_conn()

    def presigned_get_url(
        self,
        bucket: str,
        object_key: str,
        expires: timedelta = DEFAULT_URL_EXPIRY,
    ) -> str:
        """Return a presigned GET URL for an object."""

        return self.client.presigned_get_object(bucket, object_key, expires=expires)

    def object_exists(self, bucket: str, object_key: str) -> bool:
        """Return True when the object exists."""

        try:
            self.client.stat_object(bucket, object_key)
        except Exception:
            return False
        return True

    def set_governance_retention(
        self,
        bucket: str,
        object_key: str,
        retain_until: datetime,
    ) -> None:
        """Apply a governance-mode retention date to an object."""

        self.client.set_object_retention(
            bucket,
            object_key,
            Retention(GOVERNANCE, retain_until),
        )

    def delete(
        self,
        bucket: str,
        object_key: str,
        *,
        version_id: str | None = None,
        bypass_governance: bool = False,
    ) -> None:
        """Delete an object or a specific version, optionally bypassing retention."""

        if bypass_governance:
            failures = list(
                self.client.remove_objects(
                    bucket,
                    [DeleteObject(object_key, version_id=version_id)],
                    bypass_governance_mode=True,
                )
            )
            if failures:
                messages = [getattr(failure, "message", str(failure)) for failure in failures]
                raise DeleteFailedError(f"failed to delete {object_key}: {messages}")
        else:
            self.client.remove_object(bucket, object_key, version_id=version_id)
