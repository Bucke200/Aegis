"""Password hashing, JWT tokens, and TOTP helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from aegis.common.config import get_settings

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"
_hasher = PasswordHasher()


class TokenError(ValueError):
    """Raised when a token is malformed, expired, or the wrong type."""


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def _encode(claims: dict[str, Any], lifetime: timedelta) -> str:
    settings = get_settings()
    now = datetime.now(tz=UTC)
    payload = {**claims, "iat": now, "exp": now + lifetime}
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    settings = get_settings()
    return _encode(
        {"sub": str(user_id), "role": role, "type": ACCESS_TOKEN_TYPE},
        timedelta(minutes=settings.access_token_minutes),
    )


def create_refresh_token(user_id: uuid.UUID, jti: uuid.UUID) -> str:
    settings = get_settings()
    return _encode(
        {"sub": str(user_id), "jti": str(jti), "type": REFRESH_TOKEN_TYPE},
        timedelta(days=settings.refresh_token_days),
    )


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as error:
        raise TokenError(str(error)) from error
    if payload.get("type") != expected_type:
        raise TokenError(f"expected a {expected_type} token")
    return payload


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="Aegis")


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)
