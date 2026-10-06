"""Authentication and VIP-scope dependencies."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.api.security import ACCESS_TOKEN_TYPE, TokenError, decode_token
from aegis.common.db import get_session
from aegis.common.models.enums import UserRole
from aegis.common.models.ops import User, UserVipScope


def get_current_user(request: Request, session: Session = Depends(get_session)) -> User:
    """Resolve the bearer token to an active user."""

    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        payload = decode_token(header.split(" ", 1)[1], ACCESS_TOKEN_TYPE)
        user_id = uuid.UUID(payload["sub"])
    except (TokenError, ValueError, KeyError) as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from error

    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown or inactive user")
    request.state.user = user
    return user


def require_role(*roles: UserRole) -> Callable[..., User]:
    """Dependency factory enforcing one of the given roles."""

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role")
        return user

    return dependency


def scoped_vip_ids(session: Session, user: User) -> set[uuid.UUID] | None:
    """Return the user's VIP ids, or None when the role sees every VIP."""

    if user.role in (UserRole.ADMIN, UserRole.LEAD):
        return None
    return set(session.execute(select(UserVipScope.vip_id).where(UserVipScope.user_id == user.id)).scalars())


def ensure_vip_access(session: Session, user: User, vip_id: uuid.UUID) -> None:
    scopes = scoped_vip_ids(session, user)
    if scopes is None:
        return
    if vip_id not in scopes:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "VIP not in your scope")


def can_reveal_sensitive(session: Session, user: User, vip_id: uuid.UUID) -> bool:
    """Admins may reveal; everyone else needs the per-VIP grant."""

    if user.role is UserRole.ADMIN:
        return True
    scope = session.get(UserVipScope, (user.id, vip_id))
    return bool(scope and scope.can_reveal_sensitive)
