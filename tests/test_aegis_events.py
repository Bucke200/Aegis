"""Unit tests for the incident event and capture request contracts."""

from __future__ import annotations

import uuid

import pytest

from aegis.common.events import (
    CaptureRequest,
    CaptureTrigger,
    IncidentChange,
    IncidentEvent,
    parse_incident_event,
)
from aegis.common.models.enums import IncidentStatus, IncidentSubject, Severity


def test_change_values_match_the_contract() -> None:
    assert {change.value for change in IncidentChange} == {
        "created",
        "rescored",
        "status",
        "assigned",
        "note",
        "merged",
        "capture",
        "source_removed",
    }


def test_trigger_values_match_the_contract() -> None:
    assert {trigger.value for trigger in CaptureTrigger} == {
        "created",
        "rescored",
        "item_attached",
        "recapture",
    }


def _payload(change: IncidentChange) -> dict[str, object]:
    return {
        "schema": 2,
        "incident_id": str(uuid.uuid4()),
        "subject_type": "item",
        "item_id": str(uuid.uuid4()),
        "account_id": str(uuid.uuid4()),
        "campaign_id": str(uuid.uuid4()),
        "vip_ids": [str(uuid.uuid4())],
        "severity": "high",
        "previous_severity": "medium",
        "risk_score": 0.81,
        "status": "new",
        "threat_types": ["violent_threat"],
        "change": change.value,
        "actor_id": str(uuid.uuid4()),
        "assignee_id": str(uuid.uuid4()),
    }


@pytest.mark.parametrize("change", list(IncidentChange))
def test_version_2_payloads_validate_against_incident_event(change: IncidentChange) -> None:
    event = parse_incident_event(_payload(change))

    assert event.schema_version == 2
    assert event.change is change
    assert event.severity is Severity.HIGH
    assert event.previous_severity is Severity.MEDIUM
    assert event.subject_type is IncidentSubject.ITEM
    assert event.status is IncidentStatus.NEW


def test_incident_event_round_trips_through_its_payload() -> None:
    event = IncidentEvent.model_validate(_payload(IncidentChange.ASSIGNED))

    payload = event.model_dump(mode="json", by_alias=True)

    assert payload["schema"] == 2
    assert "schema_version" not in payload
    assert set(payload) == {
        "schema",
        "incident_id",
        "subject_type",
        "item_id",
        "account_id",
        "campaign_id",
        "vip_ids",
        "severity",
        "previous_severity",
        "risk_score",
        "status",
        "threat_types",
        "change",
        "actor_id",
        "assignee_id",
        "merged_into_id",
    }
    assert parse_incident_event(payload) == event


def test_version_1_created_payload_parses_with_missing_fields_as_none() -> None:
    incident_id = uuid.uuid4()
    item_id = uuid.uuid4()
    vip_id = uuid.uuid4()
    payload = {
        "incident_id": str(incident_id),
        "item_id": str(item_id),
        "severity": "high",
        "risk_score": 0.8,
        "vip_ids": [str(vip_id)],
    }

    event = parse_incident_event(payload)

    assert event.schema_version == 1
    assert event.incident_id == incident_id
    assert event.item_id == item_id
    assert event.vip_ids == [vip_id]
    assert event.severity is Severity.HIGH
    assert event.change is None
    assert event.subject_type is None
    assert event.previous_severity is None
    assert event.account_id is None
    assert event.campaign_id is None
    assert event.threat_types == []
    assert event.actor_id is None
    assert event.assignee_id is None


def test_version_1_update_payload_parses() -> None:
    payload = {
        "incident_id": str(uuid.uuid4()),
        "severity": "medium",
        "status": "under_review",
        "risk_score": 0.6,
        "vip_ids": [],
    }

    event = parse_incident_event(payload)

    assert event.schema_version == 1
    assert event.status is IncidentStatus.UNDER_REVIEW
    assert event.item_id is None


def test_merged_target_survives_parsing() -> None:
    payload = {
        "incident_id": str(uuid.uuid4()),
        "vip_ids": [],
        "merged_into_id": str(uuid.uuid4()),
    }

    event = parse_incident_event(payload)

    assert event.merged_into_id is not None
    assert event.model_dump(mode="json", by_alias=True)["merged_into_id"] == payload["merged_into_id"]


def test_capture_request_payload_is_versioned_and_identified() -> None:
    incident_id = uuid.uuid4()
    request = CaptureRequest(
        incident_id=incident_id,
        subject_type=IncidentSubject.ITEM,
        item_id=uuid.uuid4(),
        trigger=CaptureTrigger.CREATED,
    )

    payload = request.model_dump(mode="json", by_alias=True)

    assert payload["schema"] == 1
    assert payload["request_id"] == str(request.request_id)
    assert payload["requested_at"]
    assert CaptureRequest.model_validate(payload).incident_id == incident_id


def test_capture_request_requires_an_incident_and_trigger() -> None:
    with pytest.raises(ValueError, match="trigger"):
        CaptureRequest.model_validate({"schema": 1, "incident_id": str(uuid.uuid4()), "subject_type": "item"})
