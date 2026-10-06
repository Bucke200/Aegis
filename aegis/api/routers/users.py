"""Admin endpoints for per-VIP reveal permission."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from aegis.api.dependencies import require_role
from aegis.api.services.users import UserService
from aegis.common.db import get_session
from aegis.common.models.enums import UserRole
from aegis.common.models.ops import User

router = APIRouter(prefix="/users", tags=["users"])


class ScopeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    vip_id: uuid.UUID
    can_reveal_sensitive: bool


@router.put("/{user_id}/vips/{vip_id}/reveal", response_model=ScopeRead)
def grant_reveal(
    user_id: uuid.UUID,
    vip_id: uuid.UUID,
    actor: User = Depends(require_role(UserRole.ADMIN)),
    session: Session = Depends(get_session),
) -> ScopeRead:
    scope = UserService(session).grant_reveal(user_id, vip_id, actor_id=actor.id)
    return ScopeRead.model_validate(scope)


@router.delete(
    "/{user_id}/vips/{vip_id}/reveal",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_reveal(
    user_id: uuid.UUID,
    vip_id: uuid.UUID,
    actor: User = Depends(require_role(UserRole.ADMIN)),
    session: Session = Depends(get_session),
) -> None:
    UserService(session).revoke_reveal(user_id, vip_id, actor_id=actor.id)
