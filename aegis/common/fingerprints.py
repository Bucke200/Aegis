"""Sensitive-value normalization and salted hashing.

Plaintext fingerprint values are never stored or logged: they are normalized,
HMAC-hashed with each active salt, and discarded. Matching re-hashes a
candidate with every active salt, so an old salt keeps working until the value
is re-registered.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata
from dataclasses import dataclass

from aegis.common.config import Settings, get_settings
from aegis.common.models.enums import FingerprintKind

_NON_DIGITS = re.compile(r"\D+")
_NON_TOKENS = re.compile(r"[^\w\s]")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class InvalidFingerprintError(ValueError):
    """Raised when a value cannot be normalized for its kind."""


def normalize_phone(value: str, default_country_code: str = "91") -> str:
    """Normalize to E.164, assuming the default country for bare local numbers."""

    digits = _NON_DIGITS.sub("", value)
    if not digits:
        raise InvalidFingerprintError("phone number has no digits")
    if value.strip().startswith("+"):
        return "+" + digits
    if len(digits) == 10:
        return f"+{default_country_code}{digits}"
    if len(digits) == 11 and digits.startswith("0"):
        return f"+{default_country_code}{digits[1:]}"
    if len(digits) == 12 and digits.startswith(default_country_code):
        return f"+{digits}"
    return "+" + digits


def normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if not _EMAIL.match(normalized):
        raise InvalidFingerprintError("invalid email address")
    return normalized


def normalize_address(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).lower()
    tokens = sorted(set(_NON_TOKENS.sub(" ", normalized).split()))
    if not tokens:
        raise InvalidFingerprintError("address has no tokens")
    return " ".join(tokens)


def normalize_value(value: str, kind: FingerprintKind) -> str:
    """Normalize a value for its fingerprint kind."""

    if kind is FingerprintKind.PHONE:
        return normalize_phone(value)
    if kind is FingerprintKind.EMAIL:
        return normalize_email(value)
    if kind is FingerprintKind.ADDRESS_TOKEN:
        return normalize_address(value)
    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    if not normalized:
        raise InvalidFingerprintError("value is empty")
    return normalized


@dataclass(frozen=True)
class Salt:
    salt_id: str
    secret: str


def active_salts(settings: Settings | None = None) -> list[Salt]:
    """Return the current salt plus any still-active previous salts."""

    settings = settings or get_settings()
    salts = [
        Salt(
            salt_id=settings.fingerprint_salt_id,
            secret=settings.fingerprint_salt.get_secret_value(),
        )
    ]
    for entry in settings.fingerprint_previous_salts.split(","):
        stripped = entry.strip()
        if not stripped:
            continue
        salt_id, separator, secret = stripped.partition(":")
        if separator and salt_id and secret:
            salts.append(Salt(salt_id=salt_id, secret=secret))
    return salts


def hash_value(normalized: str, salt: Salt) -> str:
    """HMAC-SHA256 the normalized value under one salt."""

    return hmac.new(salt.secret.encode(), normalized.encode(), hashlib.sha256).hexdigest()
