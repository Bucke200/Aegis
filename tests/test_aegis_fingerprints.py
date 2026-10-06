"""Unit tests for fingerprint normalization and hashing."""

from __future__ import annotations

import pytest

from aegis.common.config import Settings
from aegis.common.fingerprints import (
    InvalidFingerprintError,
    Salt,
    active_salts,
    hash_value,
    normalize_address,
    normalize_email,
    normalize_phone,
    normalize_value,
)
from aegis.common.models.enums import FingerprintKind


def test_phone_normalization() -> None:
    assert normalize_phone("9000000001") == "+919000000001"
    assert normalize_phone("+91 90000 00001") == "+919000000001"
    assert normalize_phone("09000000001") == "+919000000001"
    assert normalize_phone("919000000001") == "+919000000001"


def test_phone_normalization_rejects_garbage() -> None:
    with pytest.raises(InvalidFingerprintError):
        normalize_phone("no digits here")


def test_email_normalization() -> None:
    assert normalize_email(" Vip@Example.COM ") == "vip@example.com"
    with pytest.raises(InvalidFingerprintError):
        normalize_email("not-an-email")


def test_address_normalization_is_order_insensitive() -> None:
    assert normalize_address("12, MG Road, Pune!") == normalize_address("Pune MG Road 12")


def test_normalize_dispatch() -> None:
    assert normalize_value("Vip@Example.com", FingerprintKind.EMAIL) == "vip@example.com"
    with pytest.raises(InvalidFingerprintError):
        normalize_value("", FingerprintKind.OTHER)


def test_hash_is_deterministic_and_salt_dependent() -> None:
    salt_a = Salt("a", "secret-a")
    salt_b = Salt("b", "secret-b")
    assert hash_value("+919000000001", salt_a) == hash_value("+919000000001", salt_a)
    assert hash_value("+919000000001", salt_a) != hash_value("+919000000001", salt_b)


def test_active_salts_includes_previous() -> None:
    settings = Settings(
        _env_file=None,
        fingerprint_salt_id="current",
        fingerprint_salt="s3cret",
        fingerprint_previous_salts="old:oldsecret, older:evenolds",
    )
    salts = active_salts(settings)
    assert [salt.salt_id for salt in salts] == ["current", "old", "older"]
    assert salts[0].secret == "s3cret"


def test_plaintext_is_never_logged(caplog) -> None:
    value = "+91 90000 00001"
    with caplog.at_level("DEBUG"):
        normalized = normalize_value(value, FingerprintKind.PHONE)
        hash_value(normalized, Salt("x", "secret"))
    assert value not in caplog.text
    assert "9000000001" not in caplog.text
