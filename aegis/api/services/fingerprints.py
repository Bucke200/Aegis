"""Sensitive-data fingerprint registration and matching.

Values are normalized, hashed with the active salts, and discarded. Only the
hash and salt id are stored; neither the audit log nor any response contains
the plaintext.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.api import schemas
from aegis.api.services.vips import VipNotFoundError
from aegis.common.audit import record
from aegis.common.fingerprints import active_salts, hash_value, normalize_value
from aegis.common.models.enums import FingerprintKind
from aegis.common.models.reference import VIP, SensitiveFingerprint


class FingerprintService:
    """Registers and matches salted sensitive-value fingerprints."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def register(self, vip_id: uuid.UUID, payload: schemas.FingerprintCreate) -> SensitiveFingerprint:
        vip = self.session.get(VIP, vip_id)
        if vip is None:
            raise VipNotFoundError(f"VIP {vip_id} not found")

        normalized = normalize_value(payload.value, payload.kind)
        salt = active_salts()[0]
        fingerprint = SensitiveFingerprint(
            vip_id=vip.id,
            kind=payload.kind,
            salted_hash=hash_value(normalized, salt),
            salt_id=salt.salt_id,
        )
        self.session.add(fingerprint)
        self.session.flush()
        vip.config_version += 1
        record(
            self.session,
            action="vip.fingerprint_added",
            target=str(vip.id),
            details={"kind": payload.kind.value, "salt_id": salt.salt_id},
        )
        return fingerprint

    def matches(self, vip_id: uuid.UUID, value: str, kind: FingerprintKind) -> bool:
        """Return True when a value matches any registered fingerprint hash."""

        normalized = normalize_value(value, kind)
        candidate_hashes = [hash_value(normalized, salt) for salt in active_salts()]
        found = self.session.execute(
            select(SensitiveFingerprint.id)
            .where(SensitiveFingerprint.vip_id == vip_id)
            .where(SensitiveFingerprint.kind == kind)
            .where(SensitiveFingerprint.salted_hash.in_(candidate_hashes))
            .limit(1)
        ).first()
        return found is not None

    def list(self, vip_id: uuid.UUID) -> list[SensitiveFingerprint]:
        if self.session.get(VIP, vip_id) is None:
            raise VipNotFoundError(f"VIP {vip_id} not found")
        return list(
            self.session.execute(
                select(SensitiveFingerprint)
                .where(SensitiveFingerprint.vip_id == vip_id)
                .order_by(SensitiveFingerprint.created_at)
            ).scalars()
        )

    def remove(self, vip_id: uuid.UUID, fingerprint_id: uuid.UUID) -> None:
        vip = self.session.get(VIP, vip_id)
        if vip is None:
            raise VipNotFoundError(f"VIP {vip_id} not found")
        fingerprint = self.session.get(SensitiveFingerprint, fingerprint_id)
        if fingerprint is None or fingerprint.vip_id != vip_id:
            raise VipNotFoundError("fingerprint not found")
        details = {"kind": fingerprint.kind.value, "salt_id": fingerprint.salt_id}
        self.session.delete(fingerprint)
        vip.config_version += 1
        record(
            self.session,
            action="vip.fingerprint_removed",
            target=str(vip.id),
            details=details,
        )
