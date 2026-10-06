"""Audit logging and in-process rate limiting middleware."""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from aegis.api.security import ACCESS_TOKEN_TYPE, TokenError, decode_token
from aegis.common.audit import record
from aegis.common.db import session_scope

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
AUDIT_EXEMPT_PATHS = frozenset({"/auth/login", "/auth/refresh", "/auth/logout"})


class RateLimiter:
    """Sliding-window limiter; one instance per API process."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, now: float | None = None) -> bool:
        if self.per_minute <= 0:
            return True
        current = time.monotonic() if now is None else now
        window = self._hits[key]
        while window and current - window[0] > 60:
            window.popleft()
        if len(window) >= self.per_minute:
            return False
        window.append(current)
        return True


def _rate_limit_key(request: Request) -> str:
    header = request.headers.get("Authorization")
    if header:
        return header
    return request.client.host if request.client else "anonymous"


def _actor_id(request: Request) -> uuid.UUID | None:
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    try:
        payload = decode_token(header.split(" ", 1)[1], ACCESS_TOKEN_TYPE)
        return uuid.UUID(payload["sub"])
    except (TokenError, ValueError, KeyError):
        return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        limiter: RateLimiter | None = getattr(request.app.state, "rate_limiter", None)
        if limiter is not None and not limiter.allow(_rate_limit_key(request)):
            return JSONResponse(status_code=429, content={"detail": "rate limit exceeded"})
        return await call_next(request)


class AuditMiddleware(BaseHTTPMiddleware):
    """Writes mutating requests to the audit log after the response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if request.method in MUTATING_METHODS and request.url.path not in AUDIT_EXEMPT_PATHS:
            try:
                with session_scope() as session:
                    record(
                        session,
                        action=f"{request.method} {request.url.path}",
                        target=request.url.path,
                        details={"status_code": response.status_code},
                        actor_id=_actor_id(request),
                    )
            except Exception:
                pass
        return response
