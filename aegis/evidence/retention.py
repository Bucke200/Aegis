"""Audited deletion of evidence before its retention expires."""

from __future__ import annotations

import uuid

from aegis.common.db import session_scope
from aegis.common.models.ops import AuditLog
from aegis.common.storage import ObjectStorage

RETENTION_BYPASS_ACTION = "evidence_retention_bypass"


class RetentionService:
    """Deletes evidence with the retention credential and records the bypass."""

    def __init__(self, storage: ObjectStorage | None = None) -> None:
        self._storage = storage or ObjectStorage.from_settings()

    def delete_artifact(
        self,
        bucket: str,
        object_key: str,
        *,
        reason: str,
        actor_id: uuid.UUID | None = None,
    ) -> None:
        """Delete a locked artifact before expiry and write an audit row."""

        retention_storage = self._storage.with_retention_credentials()
        retention_storage.delete(bucket, object_key, bypass_governance=True)
        with session_scope() as session:
            session.add(
                AuditLog(
                    actor_id=actor_id,
                    action=RETENTION_BYPASS_ACTION,
                    target=object_key,
                    details={"bucket": bucket, "reason": reason},
                )
            )
