"""Authentication endpoints: login, refresh rotation, logout, and MFA."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.api import schemas
from aegis.api.dependencies import get_current_user
from aegis.api.security import (
    REFRESH_TOKEN_TYPE,
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_totp_secret,
    totp_uri,
    verify_password,
    verify_totp,
)
from aegis.common.audit import record
from aegis.common.config import get_settings
from aegis.common.db import get_session
from aegis.common.models.ops import RefreshToken, User, UserVipScope

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1)
    totp_code: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class MfaEnrollResponse(BaseModel):
    secret: str
    otpauth_url: str


class MfaVerifyRequest(BaseModel):
    code: str = Field(min_length=6)


class MfaVerifyResponse(BaseModel):
    enabled: bool


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
        max_age=settings.refresh_token_days * 86400,
        path="/auth",
    )


def _issue_tokens(session: Session, user: User, response: Response) -> TokenResponse:
    settings = get_settings()
    jti = uuid.uuid4()
    session.add(
        RefreshToken(
            user_id=user.id,
            jti=jti,
            expires_at=datetime.now(tz=UTC) + timedelta(days=settings.refresh_token_days),
        )
    )
    session.flush()
    _set_refresh_cookie(response, create_refresh_token(user.id, jti))
    return TokenResponse(
        access_token=create_access_token(user.id, user.role.value),
        role=user.role.value,
    )


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    response: Response,
    session: Session = Depends(get_session),
) -> TokenResponse:
    user = session.execute(select(User).where(User.email == payload.email.strip().lower())).scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    if user.mfa_enabled and (
        not payload.totp_code or not user.totp_secret or not verify_totp(user.totp_secret, payload.totp_code)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid MFA code")
    return _issue_tokens(session, user, response)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> TokenResponse:
    settings = get_settings()
    token = request.cookies.get(settings.refresh_cookie_name)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing refresh token")
    try:
        payload = decode_token(token, REFRESH_TOKEN_TYPE)
    except TokenError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid refresh token") from error

    row = session.execute(
        select(RefreshToken).where(RefreshToken.jti == uuid.UUID(payload["jti"]))
    ).scalar_one_or_none()
    now = datetime.now(tz=UTC)
    if row is None or row.revoked_at is not None or row.expires_at < now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "refresh token is not valid")
    row.revoked_at = now

    user = session.get(User, uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown or inactive user")
    return _issue_tokens(session, user, response)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    settings = get_settings()
    token = request.cookies.get(settings.refresh_cookie_name)
    if token:
        try:
            payload = decode_token(token, REFRESH_TOKEN_TYPE)
            row = session.execute(
                select(RefreshToken).where(RefreshToken.jti == uuid.UUID(payload["jti"]))
            ).scalar_one_or_none()
            if row is not None and row.revoked_at is None:
                row.revoked_at = datetime.now(tz=UTC)
        except (TokenError, ValueError):
            pass
    response.delete_cookie(settings.refresh_cookie_name, path="/auth")


@router.get("/me", response_model=schemas.MeResponse)
def me(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> schemas.MeResponse:
    scopes = list(session.execute(select(UserVipScope).where(UserVipScope.user_id == user.id)).scalars())
    return schemas.MeResponse(
        user=schemas.UserRead.model_validate(user),
        scopes=[schemas.UserScopeRead.model_validate(scope) for scope in scopes],
    )


@router.post("/mfa/enroll", response_model=MfaEnrollResponse)
def enroll_mfa(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MfaEnrollResponse:
    secret = generate_totp_secret()
    user.totp_secret = secret
    user.mfa_enabled = False
    session.flush()
    return MfaEnrollResponse(secret=secret, otpauth_url=totp_uri(secret, user.email))


@router.post("/mfa/verify", response_model=MfaVerifyResponse)
def verify_mfa(
    payload: MfaVerifyRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MfaVerifyResponse:
    if not user.totp_secret or not verify_totp(user.totp_secret, payload.code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid MFA code")
    user.mfa_enabled = True
    record(
        session,
        action="user.mfa_enabled",
        target=str(user.id),
        details={},
        actor_id=user.id,
    )
    session.flush()
    return MfaVerifyResponse(enabled=True)
