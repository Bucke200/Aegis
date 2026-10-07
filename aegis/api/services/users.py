"""User provisioning, VIP scopes, and reveal permissions."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.api.security import hash_password
from aegis.common.audit import record
from aegis.common.models.enums import UserRole
from aegis.common.models.ops import User, UserVipScope


class UserNotFoundError(LookupError):
    """Raised when a user or scope does not exist."""


class DuplicateUserError(ValueError):
    """Raised when an email is already registered."""


class RevealPermissionError(ValueError):
    """Raised when reveal permission would be granted to a Viewer."""


class UserService:
    """Creates users and manages their VIP scopes and reveal grants."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_user(
        self,
        *,
        email: str,
        password: str,
        role: UserRole,
        display_name: str | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> User:
        normalized = email.strip().lower()
        existing = self.session.execute(select(User).where(User.email == normalized)).scalar_one_or_none()
        if existing is not None:
            raise DuplicateUserError("email already registered")
        user = User(
            email=normalized,
            display_name=display_name,
            password_hash=hash_password(password),
            role=role,
        )
        self.session.add(user)
        self.session.flush()
        record(
            self.session,
            action="user.created",
            target=str(user.id),
            details={"email": normalized, "role": role.value},
            actor_id=actor_id,
        )
        return user

    def bootstrap_admin(self, *, email: str, password: str) -> User:
        return self.create_user(email=email, password=password, role=UserRole.ADMIN)

    def list_users(self) -> list[User]:
        return list(self.session.execute(select(User).order_by(User.created_at)).scalars())

    def list_directory(self) -> list[User]:
        """Active users, for the incident assignee picker."""

        return list(
            self.session.execute(
                select(User).where(User.is_active.is_(True)).order_by(User.display_name, User.email)
            ).scalars()
        )

    def get_user(self, user_id: uuid.UUID) -> User:
        user = self.session.get(User, user_id)
        if user is None:
            raise UserNotFoundError(f"user {user_id} not found")
        return user

    def set_scope(
        self,
        user_id: uuid.UUID,
        vip_id: uuid.UUID,
        *,
        can_reveal_sensitive: bool = False,
        actor_id: uuid.UUID | None = None,
    ) -> UserVipScope:
        user = self.get_user(user_id)
        if can_reveal_sensitive and user.role is UserRole.VIEWER:
            raise RevealPermissionError("Viewers can never hold reveal permission")
        scope = self.session.get(UserVipScope, (user_id, vip_id))
        if scope is None:
            scope = UserVipScope(
                user_id=user_id,
                vip_id=vip_id,
                can_reveal_sensitive=can_reveal_sensitive,
            )
            self.session.add(scope)
        else:
            scope.can_reveal_sensitive = can_reveal_sensitive
        self.session.flush()
        record(
            self.session,
            action="user.scope_set",
            target=str(user_id),
            details={
                "vip_id": str(vip_id),
                "can_reveal_sensitive": can_reveal_sensitive,
            },
            actor_id=actor_id,
        )
        return scope

    def grant_reveal(self, user_id: uuid.UUID, vip_id: uuid.UUID, *, actor_id: uuid.UUID | None = None) -> UserVipScope:
        return self.set_scope(user_id, vip_id, can_reveal_sensitive=True, actor_id=actor_id)

    def revoke_reveal(
        self, user_id: uuid.UUID, vip_id: uuid.UUID, *, actor_id: uuid.UUID | None = None
    ) -> UserVipScope:
        return self.set_scope(user_id, vip_id, can_reveal_sensitive=False, actor_id=actor_id)

    def update_user(
        self,
        user_id: uuid.UUID,
        *,
        display_name: str | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> User:
        user = self.get_user(user_id)
        changes: dict[str, Any] = {}
        if display_name is not None and display_name != user.display_name:
            changes["display_name"] = {"from": user.display_name, "to": display_name}
            user.display_name = display_name
        if role is not None and role != user.role:
            changes["role"] = {"from": user.role.value, "to": role.value}
            user.role = role
            if role is UserRole.VIEWER:
                self._clear_reveal_grants(user.id)
        if is_active is not None and is_active != user.is_active:
            changes["is_active"] = {"from": user.is_active, "to": is_active}
            user.is_active = is_active
        if changes:
            record(
                self.session,
                action="user.updated",
                target=str(user.id),
                details=changes,
                actor_id=actor_id,
            )
            self.session.flush()
        return user

    def reset_password(self, user_id: uuid.UUID, password: str) -> User:
        user = self.get_user(user_id)
        user.password_hash = hash_password(password)
        record(
            self.session,
            action="user.password_reset",
            target=str(user.id),
            details={},
        )
        self.session.flush()
        return user

    def remove_scope(self, user_id: uuid.UUID, vip_id: uuid.UUID, *, actor_id: uuid.UUID | None = None) -> None:
        scope = self.session.get(UserVipScope, (user_id, vip_id))
        if scope is None:
            raise UserNotFoundError("scope not found")
        self.session.delete(scope)
        record(
            self.session,
            action="user.scope_removed",
            target=str(user_id),
            details={"vip_id": str(vip_id)},
            actor_id=actor_id,
        )

    def _clear_reveal_grants(self, user_id: uuid.UUID) -> None:
        scopes = self.session.execute(select(UserVipScope).where(UserVipScope.user_id == user_id)).scalars()
        for scope in scopes:
            scope.can_reveal_sensitive = False

    def get_user_by_email(self, email: str) -> User:
        user = self.session.execute(select(User).where(User.email == email.strip().lower())).scalar_one_or_none()
        if user is None:
            raise UserNotFoundError(f"user {email} not found")
        return user
