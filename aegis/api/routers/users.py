"""Admin endpoints for users, VIP scopes, and reveal permission."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from aegis.api import schemas
from aegis.api.dependencies import require_role
from aegis.api.services.users import UserService
from aegis.common.db import get_session
from aegis.common.models.enums import UserRole
from aegis.common.models.ops import User

router = APIRouter(prefix="/users", tags=["users"])

AdminOnly = Depends(require_role(UserRole.ADMIN))
AnalystOrAbove = Depends(require_role(UserRole.ANALYST, UserRole.LEAD, UserRole.ADMIN))


def get_user_service(session: Session = Depends(get_session)) -> UserService:
    return UserService(session)


@router.get("", response_model=list[schemas.UserRead])
def list_users(
    actor: User = AdminOnly,
    service: UserService = Depends(get_user_service),
) -> list[schemas.UserRead]:
    return [schemas.UserRead.model_validate(user) for user in service.list_users()]


@router.get("/directory", response_model=list[schemas.UserSummary])
def list_directory(
    actor: User = AnalystOrAbove,
    service: UserService = Depends(get_user_service),
) -> list[schemas.UserSummary]:
    return [schemas.UserSummary.model_validate(user) for user in service.list_directory()]


@router.post("", response_model=schemas.UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: schemas.UserCreate,
    actor: User = AdminOnly,
    service: UserService = Depends(get_user_service),
) -> schemas.UserRead:
    user = service.create_user(
        email=payload.email,
        password=payload.password,
        role=payload.role,
        display_name=payload.display_name,
        actor_id=actor.id,
    )
    return schemas.UserRead.model_validate(user)


@router.get("/{user_id}", response_model=schemas.UserRead)
def get_user(
    user_id: uuid.UUID,
    actor: User = AdminOnly,
    service: UserService = Depends(get_user_service),
) -> schemas.UserRead:
    return schemas.UserRead.model_validate(service.get_user(user_id))


@router.patch("/{user_id}", response_model=schemas.UserRead)
def update_user(
    user_id: uuid.UUID,
    payload: schemas.UserUpdate,
    actor: User = AdminOnly,
    service: UserService = Depends(get_user_service),
) -> schemas.UserRead:
    user = service.update_user(
        user_id,
        display_name=payload.display_name,
        role=payload.role,
        is_active=payload.is_active,
        actor_id=actor.id,
    )
    return schemas.UserRead.model_validate(user)


@router.put("/{user_id}/vips/{vip_id}", response_model=schemas.UserScopeRead)
def assign_scope(
    user_id: uuid.UUID,
    vip_id: uuid.UUID,
    payload: schemas.ScopeAssignRequest,
    actor: User = AdminOnly,
    service: UserService = Depends(get_user_service),
) -> schemas.UserScopeRead:
    scope = service.set_scope(
        user_id,
        vip_id,
        can_reveal_sensitive=payload.can_reveal_sensitive,
        actor_id=actor.id,
    )
    return schemas.UserScopeRead.model_validate(scope)


@router.delete(
    "/{user_id}/vips/{vip_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_scope(
    user_id: uuid.UUID,
    vip_id: uuid.UUID,
    actor: User = AdminOnly,
    service: UserService = Depends(get_user_service),
) -> None:
    service.remove_scope(user_id, vip_id, actor_id=actor.id)


@router.put("/{user_id}/vips/{vip_id}/reveal", response_model=schemas.UserScopeRead)
def grant_reveal(
    user_id: uuid.UUID,
    vip_id: uuid.UUID,
    actor: User = AdminOnly,
    service: UserService = Depends(get_user_service),
) -> schemas.UserScopeRead:
    scope = service.grant_reveal(user_id, vip_id, actor_id=actor.id)
    return schemas.UserScopeRead.model_validate(scope)


@router.delete(
    "/{user_id}/vips/{vip_id}/reveal",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_reveal(
    user_id: uuid.UUID,
    vip_id: uuid.UUID,
    actor: User = AdminOnly,
    service: UserService = Depends(get_user_service),
) -> None:
    service.revoke_reveal(user_id, vip_id, actor_id=actor.id)
