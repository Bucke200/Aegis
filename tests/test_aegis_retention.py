"""Unit tests for the audited retention service."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast
from unittest.mock import Mock

from aegis.common.storage import ObjectStorage
from aegis.evidence.retention import RETENTION_BYPASS_ACTION, RetentionService


def test_delete_artifact_bypasses_retention_and_audits(monkeypatch) -> None:
    storage = Mock(spec=ObjectStorage)
    retention_storage = Mock()
    storage.with_retention_credentials.return_value = retention_storage
    session = Mock()

    @contextmanager
    def fake_session_scope() -> Iterator[Mock]:
        yield session

    monkeypatch.setattr("aegis.evidence.retention.session_scope", fake_session_scope)
    actor_id = uuid.uuid4()

    service = RetentionService(cast(ObjectStorage, storage))
    service.delete_artifact(
        "aegis-evidence",
        "evidence/x",
        reason="dpdp erasure",
        actor_id=actor_id,
    )

    retention_storage.delete.assert_called_once_with("aegis-evidence", "evidence/x", bypass_governance=True)
    audit = session.add.call_args.args[0]
    assert audit.action == RETENTION_BYPASS_ACTION
    assert audit.target == "evidence/x"
    assert audit.actor_id == actor_id
    assert audit.details == {"bucket": "aegis-evidence", "reason": "dpdp erasure"}
