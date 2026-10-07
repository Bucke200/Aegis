"""Incident queries, workflow transitions, notes, assignment, and bulk actions."""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import case, literal, or_, select, tuple_
from sqlalchemy.orm import Session

from aegis.api.dependencies import scoped_vip_ids
from aegis.common.models.collected import Account, Item
from aegis.common.models.enums import (
    IncidentEventType,
    IncidentOutcome,
    IncidentStatus,
    LabelKind,
    UserRole,
)
from aegis.common.models.incidents import (
    Campaign,
    Detection,
    Incident,
    IncidentEvent,
    IncidentNote,
    IncidentVip,
)
from aegis.common.models.ops import EvidenceArtifact, Label, User
from aegis.common.outbox import INCIDENT_UPDATED, enqueue

SEVERITY_RANKS = {"low": 0, "medium": 1, "high": 2, "critical": 3}
ALLOWED_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
    IncidentStatus.NEW: {IncidentStatus.UNDER_REVIEW},
    IncidentStatus.UNDER_REVIEW: {
        IncidentStatus.ESCALATED,
        IncidentStatus.RESOLVED,
        IncidentStatus.FALSE_POSITIVE,
    },
    IncidentStatus.ESCALATED: {IncidentStatus.RESOLVED, IncidentStatus.FALSE_POSITIVE},
    IncidentStatus.RESOLVED: {IncidentStatus.UNDER_REVIEW},
    IncidentStatus.FALSE_POSITIVE: {IncidentStatus.UNDER_REVIEW},
}
REOPEN_FROM = {IncidentStatus.RESOLVED, IncidentStatus.FALSE_POSITIVE}
EDIT_ROLES = {UserRole.ANALYST, UserRole.LEAD, UserRole.ADMIN}
REOPEN_ROLES = {UserRole.LEAD, UserRole.ADMIN}


class IncidentNotFoundError(LookupError):
    """Raised when an incident is missing or outside the user's scope."""


class InvalidTransitionError(ValueError):
    """Raised when a status transition is not allowed for the caller."""


class OutcomeRequiredError(ValueError):
    """Raised when resolving an incident without an analyst outcome."""


class MergeReadOnlyError(ValueError):
    """Raised when changing a merged (read-only) incident."""


@dataclass
class IncidentFilters:
    severity: list[str] = field(default_factory=list)
    status: list[str] = field(default_factory=list)
    source: list[str] = field(default_factory=list)
    language: list[str] = field(default_factory=list)
    vip_ids: list[uuid.UUID] = field(default_factory=list)
    assignee_ids: list[uuid.UUID] = field(default_factory=list)
    campaign_id: uuid.UUID | None = None
    threat_types: list[str] = field(default_factory=list)
    created_from: datetime | None = None
    created_to: datetime | None = None
    include_merged: bool = False


class IncidentService:
    """Read and workflow operations over incidents, scoped to the caller."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def _scope_condition(self, user: User) -> Any:
        scopes = scoped_vip_ids(self.session, user)
        if scopes is None:
            return None
        return Incident.id.in_(select(IncidentVip.incident_id).where(IncidentVip.vip_id.in_(scopes)))

    def _apply_filters(self, stmt: Any, filters: IncidentFilters) -> Any:
        if not filters.include_merged:
            stmt = stmt.where(Incident.merged_into_id.is_(None))
        if filters.severity:
            stmt = stmt.where(Incident.severity.in_(filters.severity))
        if filters.status:
            stmt = stmt.where(Incident.status.in_(filters.status))
        if filters.source:
            stmt = stmt.where(Incident.source.in_(filters.source))
        if filters.language:
            stmt = stmt.where(Incident.language.in_(filters.language))
        if filters.assignee_ids:
            stmt = stmt.where(Incident.assignee_id.in_(filters.assignee_ids))
        if filters.campaign_id is not None:
            stmt = stmt.where(Incident.campaign_id == filters.campaign_id)
        if filters.threat_types:
            stmt = stmt.where(Incident.threat_types.overlap(filters.threat_types))
        if filters.vip_ids:
            stmt = stmt.where(
                Incident.id.in_(select(IncidentVip.incident_id).where(IncidentVip.vip_id.in_(filters.vip_ids)))
            )
        if filters.created_from is not None:
            stmt = stmt.where(Incident.created_at >= filters.created_from)
        if filters.created_to is not None:
            stmt = stmt.where(Incident.created_at <= filters.created_to)
        return stmt

    def _enrich(self, incidents: list[Incident]) -> list[Incident]:
        """Attach VIP ids, item, account, and assignee for the API response."""

        if not incidents:
            return incidents
        incident_ids = [incident.id for incident in incidents]
        vip_map: dict[uuid.UUID, list[uuid.UUID]] = {incident_id: [] for incident_id in incident_ids}
        for incident_id, vip_id in self.session.execute(
            select(IncidentVip.incident_id, IncidentVip.vip_id).where(IncidentVip.incident_id.in_(incident_ids))
        ):
            vip_map[incident_id].append(vip_id)

        item_ids = {incident.item_id for incident in incidents if incident.item_id is not None}
        items = (
            {row.id: row for row in self.session.execute(select(Item).where(Item.id.in_(item_ids))).scalars()}
            if item_ids
            else {}
        )
        account_ids = {incident.account_id for incident in incidents if incident.account_id is not None}
        for incident in incidents:
            item = items.get(incident.item_id) if incident.item_id is not None else None
            if item is not None and item.account_id is not None:
                account_ids.add(item.account_id)
        accounts = (
            {row.id: row for row in self.session.execute(select(Account).where(Account.id.in_(account_ids))).scalars()}
            if account_ids
            else {}
        )
        assignee_ids = {incident.assignee_id for incident in incidents if incident.assignee_id is not None}
        assignees = (
            {row.id: row for row in self.session.execute(select(User).where(User.id.in_(assignee_ids))).scalars()}
            if assignee_ids
            else {}
        )

        for incident in incidents:
            item = items.get(incident.item_id) if incident.item_id is not None else None
            account = accounts.get(incident.account_id) if incident.account_id is not None else None
            if account is None and item is not None and item.account_id is not None:
                account = accounts.get(item.account_id)
            setattr(incident, "vip_ids", sorted(vip_map[incident.id], key=str))  # noqa: B010
            setattr(incident, "item", item)  # noqa: B010
            setattr(incident, "account", account)  # noqa: B010
            assignee = assignees.get(incident.assignee_id) if incident.assignee_id is not None else None
            setattr(incident, "assignee", assignee)  # noqa: B010
        return incidents

    def list_incidents(
        self,
        user: User,
        filters: IncidentFilters,
        *,
        sort: str = "time",
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[Incident], str | None]:
        stmt = self._apply_filters(select(Incident), filters)
        scope = self._scope_condition(user)
        if scope is not None:
            stmt = stmt.where(scope)

        severity_rank = case(
            *[(Incident.severity == name, rank) for name, rank in SEVERITY_RANKS.items()],
            else_=0,
        )
        if sort == "severity":
            stmt = stmt.order_by(severity_rank.desc(), Incident.created_at.desc(), Incident.id.desc())
        else:
            stmt = stmt.order_by(Incident.created_at.desc(), Incident.id.desc())

        if cursor:
            cursor_values = _decode_cursor(cursor)
            cursor_id = uuid.UUID(cursor_values["id"])
            if sort == "severity":
                stmt = stmt.where(
                    tuple_(severity_rank, Incident.created_at, Incident.id)
                    < tuple_(
                        literal(cursor_values["rank"]),
                        literal(cursor_values["ts"]),
                        literal(cursor_id),
                    )
                )
            else:
                stmt = stmt.where(
                    tuple_(Incident.created_at, Incident.id) < tuple_(literal(cursor_values["ts"]), literal(cursor_id))
                )

        rows = list(self.session.execute(stmt.limit(limit + 1)).scalars())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            last = rows[-1]
            next_cursor = _encode_cursor(sort, SEVERITY_RANKS.get(last.severity.value, 0), last.created_at, last.id)
        return self._enrich(rows), next_cursor

    def get_incident(self, user: User, incident_id: uuid.UUID) -> Incident:
        incident = self.session.get(Incident, incident_id)
        if incident is None:
            raise IncidentNotFoundError(f"incident {incident_id} not found")
        scope = self._scope_condition(user)
        if (
            scope is not None
            and not self.session.execute(
                select(IncidentVip.incident_id).where(IncidentVip.incident_id == incident_id).where(scope)
            ).first()
        ):
            raise IncidentNotFoundError(f"incident {incident_id} not in your scope")
        return incident

    def detail(self, user: User, incident_id: uuid.UUID) -> dict[str, Any]:
        incident = self.get_incident(user, incident_id)
        self._enrich([incident])
        detections = list(
            self.session.execute(
                select(Detection).where(
                    or_(
                        Detection.item_id == incident.item_id,
                        Detection.account_id == incident.account_id,
                    )
                )
            ).scalars()
        )
        account_id = incident.account_id
        if account_id is None and incident.item_id is not None:
            item = self.session.get(Item, incident.item_id)
            account_id = item.account_id if item else None
        account = self.session.get(Account, account_id) if account_id else None
        campaign = self.session.get(Campaign, incident.campaign_id) if incident.campaign_id else None
        history = list(
            self.session.execute(
                select(IncidentEvent).where(IncidentEvent.incident_id == incident_id).order_by(IncidentEvent.at)
            ).scalars()
        )
        notes = list(
            self.session.execute(
                select(IncidentNote).where(IncidentNote.incident_id == incident_id).order_by(IncidentNote.created_at)
            ).scalars()
        )
        evidence = list(
            self.session.execute(
                select(EvidenceArtifact)
                .where(EvidenceArtifact.incident_id == incident_id)
                .order_by(EvidenceArtifact.captured_at)
            ).scalars()
        )
        return {
            "incident": incident,
            "detections": detections,
            "account": account,
            "campaign": campaign,
            "history": history,
            "notes": notes,
            "evidence": evidence,
        }

    def transition_status(
        self,
        user: User,
        incident_id: uuid.UUID,
        target: IncidentStatus,
        *,
        reason: str | None = None,
        outcome: IncidentOutcome | None = None,
    ) -> Incident:
        incident = self.get_incident(user, incident_id)
        if incident.merged_into_id is not None:
            raise MergeReadOnlyError("merged incidents are read-only apart from notes")
        if user.role not in EDIT_ROLES:
            raise InvalidTransitionError("viewers cannot change incident status")

        current = incident.status
        if target not in ALLOWED_TRANSITIONS.get(current, set()):
            raise InvalidTransitionError(f"cannot move from {current.value} to {target.value}")

        if current in REOPEN_FROM:
            if user.role not in REOPEN_ROLES:
                raise InvalidTransitionError("only a Lead or Admin can reopen an incident")
            if not reason:
                raise InvalidTransitionError("reopening requires a reason")
        if target is IncidentStatus.RESOLVED:
            if outcome is None:
                raise OutcomeRequiredError("resolving requires an outcome")
            if outcome is IncidentOutcome.BELOW_THRESHOLD:
                raise OutcomeRequiredError("'below_threshold' is a system-only outcome")
            incident.outcome = outcome

        incident.status = target
        self.session.add(
            IncidentEvent(
                incident_id=incident.id,
                actor_id=user.id,
                event_type=IncidentEventType.STATUS_CHANGE,
                from_value={"status": current.value},
                to_value={"status": target.value, "outcome": outcome.value if outcome else None},
                reason=reason,
            )
        )
        if target is IncidentStatus.FALSE_POSITIVE:
            self.session.add(
                Label(
                    item_id=incident.item_id,
                    incident_id=incident.id,
                    account_id=incident.account_id,
                    labeller_id=user.id,
                    label=LabelKind.FALSE_POSITIVE,
                )
            )
        self._publish_update(incident)
        return incident

    def assign(self, user: User, incident_id: uuid.UUID, assignee_id: uuid.UUID) -> Incident:
        incident = self.get_incident(user, incident_id)
        if user.role not in EDIT_ROLES:
            raise InvalidTransitionError("viewers cannot assign incidents")
        if self.session.get(User, assignee_id) is None:
            raise IncidentNotFoundError(f"assignee {assignee_id} not found")
        previous = incident.assignee_id
        incident.assignee_id = assignee_id
        self.session.add(
            IncidentEvent(
                incident_id=incident.id,
                actor_id=user.id,
                event_type=IncidentEventType.ASSIGN,
                from_value={"assignee_id": str(previous) if previous else None},
                to_value={"assignee_id": str(assignee_id)},
            )
        )
        self._publish_update(incident)
        return incident

    def add_note(self, user: User, incident_id: uuid.UUID, body: str) -> IncidentNote:
        incident = self.get_incident(user, incident_id)
        note = IncidentNote(incident_id=incident.id, author_id=user.id, body=body)
        self.session.add(note)
        self.session.flush()
        self.session.add(
            IncidentEvent(
                incident_id=incident.id,
                actor_id=user.id,
                event_type=IncidentEventType.NOTE,
                to_value={"note_id": str(note.id)},
            )
        )
        return note

    def bulk_transition(
        self,
        user: User,
        incident_ids: list[uuid.UUID],
        target: IncidentStatus,
        *,
        reason: str | None = None,
        outcome: IncidentOutcome | None = None,
    ) -> tuple[int, list[str]]:
        applied = 0
        errors: list[str] = []
        targets: set[uuid.UUID] = set()
        for incident_id in incident_ids:
            incident = self.session.get(Incident, incident_id)
            if incident is None:
                errors.append(f"{incident_id}: not found")
                continue
            live_id = incident.merged_into_id or incident.id
            if live_id in targets:
                continue
            targets.add(live_id)
            try:
                self.transition_status(user, live_id, target, reason=reason, outcome=outcome)
                applied += 1
            except (InvalidTransitionError, OutcomeRequiredError, MergeReadOnlyError) as error:
                errors.append(f"{incident_id}: {error}")
        return applied, errors

    def _publish_update(self, incident: Incident) -> None:
        vip_ids = list(
            self.session.execute(select(IncidentVip.vip_id).where(IncidentVip.incident_id == incident.id)).scalars()
        )
        enqueue(
            self.session,
            INCIDENT_UPDATED,
            {
                "incident_id": str(incident.id),
                "severity": incident.severity.value,
                "status": incident.status.value,
                "risk_score": incident.risk_score,
                "vip_ids": [str(vip_id) for vip_id in vip_ids],
            },
        )


def _encode_cursor(sort: str, rank: int, created_at: datetime, incident_id: uuid.UUID) -> str:
    payload = json.dumps({"sort": sort, "rank": rank, "ts": created_at.isoformat(), "id": str(incident_id)})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(cursor: str) -> dict[str, Any]:
    decoded: dict[str, Any] = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    decoded["ts"] = datetime.fromisoformat(decoded["ts"])
    return decoded
