"""VIP configuration service.

Every mutation appends an ``audit_log`` row and bumps ``vips.config_version``
so workers invalidate cached configuration within the five-minute requirement.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aegis.api import schemas
from aegis.common.audit import record
from aegis.common.models.enums import AliasKind
from aegis.common.models.reference import (
    VIP,
    OfficialAccount,
    VipAlias,
    VipContextKeyword,
)


class VipNotFoundError(LookupError):
    """Raised when a VIP or one of its child records does not exist."""


class DuplicateVipConfigError(ValueError):
    """Raised when a change would create a duplicate configuration row."""


class VipService:
    """CRUD for VIPs, aliases, context keywords, and official accounts."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_vip(self, payload: schemas.VipCreate) -> VIP:
        vip = VIP(
            name=payload.name,
            sensitivity=payload.sensitivity,
            monitoring_active=payload.monitoring_active,
        )
        self.session.add(vip)
        self.session.flush()
        record(
            self.session,
            action="vip.created",
            target=str(vip.id),
            details={
                "name": vip.name,
                "sensitivity": vip.sensitivity.value,
                "monitoring_active": vip.monitoring_active,
            },
        )
        return vip

    def list_vips(self) -> list[VIP]:
        return list(self.session.execute(select(VIP).order_by(VIP.created_at)).scalars())

    def get_vip(self, vip_id: uuid.UUID) -> VIP:
        vip = self.session.get(VIP, vip_id)
        if vip is None:
            raise VipNotFoundError(f"VIP {vip_id} not found")
        return vip

    def update_vip(self, vip_id: uuid.UUID, payload: schemas.VipUpdate) -> VIP:
        vip = self.get_vip(vip_id)
        changes: dict[str, Any] = {}

        if payload.name is not None and payload.name != vip.name:
            changes["name"] = {"from": vip.name, "to": payload.name}
            vip.name = payload.name
        if payload.sensitivity is not None and payload.sensitivity != vip.sensitivity:
            changes["sensitivity"] = {"from": vip.sensitivity.value, "to": payload.sensitivity.value}
            vip.sensitivity = payload.sensitivity

        monitoring_changed = (
            payload.monitoring_active is not None and payload.monitoring_active != vip.monitoring_active
        )
        if monitoring_changed:
            changes["monitoring_active"] = {
                "from": vip.monitoring_active,
                "to": payload.monitoring_active,
            }
            vip.monitoring_active = bool(payload.monitoring_active)

        if not changes:
            return vip

        self._bump(vip)
        if monitoring_changed:
            action = "vip.monitoring_resumed" if payload.monitoring_active else "vip.monitoring_paused"
        else:
            action = "vip.updated"
        record(self.session, action=action, target=str(vip.id), details=changes)
        self.session.flush()
        return vip

    def list_aliases(self, vip_id: uuid.UUID) -> list[VipAlias]:
        self.get_vip(vip_id)
        return list(
            self.session.execute(select(VipAlias).where(VipAlias.vip_id == vip_id).order_by(VipAlias.alias)).scalars()
        )

    def add_alias(self, vip_id: uuid.UUID, payload: schemas.AliasCreate) -> VipAlias:
        vip = self.get_vip(vip_id)
        alias = VipAlias(
            vip_id=vip.id,
            alias=payload.alias,
            kind=payload.kind,
            is_ambiguous=payload.is_ambiguous,
        )
        self.session.add(alias)
        try:
            self.session.flush()
        except IntegrityError as error:
            raise DuplicateVipConfigError("alias already exists") from error
        self._bump(vip)
        record(
            self.session,
            action="vip.alias_added",
            target=str(vip.id),
            details={"alias": alias.alias, "kind": alias.kind.value, "is_ambiguous": alias.is_ambiguous},
        )
        return alias

    def remove_alias(self, vip_id: uuid.UUID, alias: str, kind: AliasKind) -> None:
        vip = self.get_vip(vip_id)
        row = self.session.get(VipAlias, (vip_id, alias, kind))
        if row is None:
            raise VipNotFoundError("alias not found")
        self.session.delete(row)
        self._bump(vip)
        record(
            self.session,
            action="vip.alias_removed",
            target=str(vip.id),
            details={"alias": alias, "kind": kind},
        )

    def list_context_keywords(self, vip_id: uuid.UUID) -> list[VipContextKeyword]:
        self.get_vip(vip_id)
        return list(
            self.session.execute(
                select(VipContextKeyword).where(VipContextKeyword.vip_id == vip_id).order_by(VipContextKeyword.keyword)
            ).scalars()
        )

    def add_context_keyword(self, vip_id: uuid.UUID, payload: schemas.ContextKeywordCreate) -> VipContextKeyword:
        vip = self.get_vip(vip_id)
        keyword = VipContextKeyword(vip_id=vip.id, keyword=payload.keyword)
        self.session.add(keyword)
        try:
            self.session.flush()
        except IntegrityError as error:
            raise DuplicateVipConfigError("context keyword already exists") from error
        self._bump(vip)
        record(
            self.session,
            action="vip.context_keyword_added",
            target=str(vip.id),
            details={"keyword": keyword.keyword},
        )
        return keyword

    def remove_context_keyword(self, vip_id: uuid.UUID, keyword: str) -> None:
        vip = self.get_vip(vip_id)
        row = self.session.get(VipContextKeyword, (vip_id, keyword))
        if row is None:
            raise VipNotFoundError("context keyword not found")
        self.session.delete(row)
        self._bump(vip)
        record(
            self.session,
            action="vip.context_keyword_removed",
            target=str(vip.id),
            details={"keyword": keyword},
        )

    def list_official_accounts(self, vip_id: uuid.UUID) -> list[OfficialAccount]:
        self.get_vip(vip_id)
        return list(self.session.execute(select(OfficialAccount).where(OfficialAccount.vip_id == vip_id)).scalars())

    def add_official_account(self, vip_id: uuid.UUID, payload: schemas.OfficialAccountCreate) -> OfficialAccount:
        vip = self.get_vip(vip_id)
        account = OfficialAccount(
            vip_id=vip.id,
            source=payload.source,
            platform_account_id=payload.platform_account_id,
            handle=payload.handle,
            display_name=payload.display_name,
            bio=payload.bio,
            avatar_object_key=payload.avatar_object_key,
            verification_evidence=payload.verification_evidence,
            verified_at=datetime.now(tz=UTC) if payload.verification_evidence else None,
        )
        self.session.add(account)
        try:
            self.session.flush()
        except IntegrityError as error:
            raise DuplicateVipConfigError("official account already registered for this source") from error
        self._bump(vip)
        record(
            self.session,
            action="vip.official_account_added",
            target=str(vip.id),
            details={
                "source": account.source.value,
                "platform_account_id": account.platform_account_id,
                "handle": account.handle,
                "verified": account.verified_at is not None,
            },
        )
        return account

    def remove_official_account(self, vip_id: uuid.UUID, account_id: uuid.UUID) -> None:
        vip = self.get_vip(vip_id)
        account = self.session.get(OfficialAccount, account_id)
        if account is None or account.vip_id != vip_id:
            raise VipNotFoundError("official account not found")
        details = {"source": account.source.value, "handle": account.handle}
        self.session.delete(account)
        self._bump(vip)
        record(
            self.session,
            action="vip.official_account_removed",
            target=str(vip.id),
            details=details,
        )

    @staticmethod
    def _bump(vip: VIP) -> None:
        vip.config_version += 1
