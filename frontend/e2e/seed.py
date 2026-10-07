"""Seed the E2E environment: admin users, one VIP with aliases, and a replay fixture.

Run from the repository root after migrations:

    uv run python frontend/e2e/seed.py
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from aegis.api.services.users import UserService
from aegis.collectors.synthetic import SyntheticConfig, generate
from aegis.common.db import session_scope
from aegis.common.models.enums import AliasKind, Sensitivity, UserRole
from aegis.common.models.ops import User
from aegis.common.models.reference import VIP, VipAlias

FIXTURE_PATH = Path(__file__).resolve().parent / ".artifacts" / "incident.jsonl"
VIP_NAME = "E2E VIP"
THREAT_TEXT = "I will shoot e2e vip with a gun and bomb tomorrow at his house"
ADMIN_USERS = (
    ("e2e-admin@example.test", "e2e-admin-password", "E2E Admin"),
    ("e2e-mfa@example.test", "e2e-mfa-password", "E2E MFA"),
)


def seed_users() -> None:
    with session_scope() as session:
        service = UserService(session)
        for email, password, display_name in ADMIN_USERS:
            existing = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
            if existing is None:
                service.create_user(
                    email=email,
                    password=password,
                    role=UserRole.ADMIN,
                    display_name=display_name,
                )


def seed_vip() -> None:
    with session_scope() as session:
        vip = session.execute(select(VIP).where(VIP.name == VIP_NAME)).scalar_one_or_none()
        if vip is None:
            vip = VIP(name=VIP_NAME, sensitivity=Sensitivity.HIGH)
            session.add(vip)
            session.flush()
        existing = {
            (row.alias, row.kind)
            for row in session.execute(select(VipAlias).where(VipAlias.vip_id == vip.id)).scalars()
        }
        for alias, kind in ((VIP_NAME, AliasKind.NAME), ("e2evip", AliasKind.NICKNAME)):
            if (alias, kind) not in existing:
                session.add(VipAlias(vip_id=vip.id, alias=alias, kind=kind))


def write_fixture() -> None:
    items = generate(
        SyntheticConfig(
            seed=1234,
            campaign_accounts=1,
            impersonators=0,
            leaks=0,
            hinglish_threats=0,
            criticism=0,
            vip_name=VIP_NAME,
        )
    )
    payload = json.loads(items[0].model_dump_json())
    payload["content"]["text"] = THREAT_TEXT
    payload["author"]["followers"] = 1_000_000
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def main() -> int:
    seed_users()
    seed_vip()
    write_fixture()
    print(f"seeded E2E users, VIP '{VIP_NAME}', and {FIXTURE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
