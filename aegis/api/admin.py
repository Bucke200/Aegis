"""``aegis-admin``: bootstrap and manage users from the command line."""

from __future__ import annotations

import argparse
import uuid
from collections.abc import Sequence

from aegis.api.services.users import UserService
from aegis.common.db import session_scope
from aegis.common.logging import configure_logging
from aegis.common.models.enums import UserRole


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aegis-admin", description="Aegis user and access administration")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create-user", help="create a user")
    create.add_argument("--email", required=True)
    create.add_argument("--password", required=True)
    create.add_argument("--role", choices=[role.value for role in UserRole], default=UserRole.VIEWER.value)
    create.add_argument("--display-name", default=None)

    bootstrap = subparsers.add_parser("create-admin", help="create the first admin")
    bootstrap.add_argument("--email", required=True)
    bootstrap.add_argument("--password", required=True)

    subparsers.add_parser("list-users", help="list users and roles")

    reset = subparsers.add_parser("reset-password", help="reset a user's password")
    reset.add_argument("--email", required=True)
    reset.add_argument("--password", required=True)

    scope = subparsers.add_parser("set-scope", help="assign a VIP to a user")
    scope.add_argument("--email", required=True)
    scope.add_argument("--vip-id", required=True)
    scope.add_argument("--reveal", action="store_true")

    reveal = subparsers.add_parser("grant-reveal", help="grant reveal permission for a VIP")
    reveal.add_argument("--email", required=True)
    reveal.add_argument("--vip-id", required=True)

    return parser


def _run(args: argparse.Namespace) -> int:
    with session_scope() as session:
        service = UserService(session)
        if args.command == "create-user":
            user = service.create_user(
                email=args.email,
                password=args.password,
                role=UserRole(args.role),
                display_name=args.display_name,
            )
            print(f"created {user.role.value} {user.email} ({user.id})")
        elif args.command == "create-admin":
            user = service.bootstrap_admin(email=args.email, password=args.password)
            print(f"created admin {user.email} ({user.id})")
        elif args.command == "list-users":
            for user in service.list_users():
                state = "active" if user.is_active else "inactive"
                print(f"{user.email}\t{user.role.value}\t{state}\t{user.id}")
        elif args.command == "reset-password":
            user = service.get_user_by_email(args.email)
            service.reset_password(user.id, args.password)
            print(f"password reset for {user.email}")
        elif args.command == "set-scope":
            user = service.get_user_by_email(args.email)
            scope = service.set_scope(
                user.id,
                uuid.UUID(args.vip_id),
                can_reveal_sensitive=bool(args.reveal),
            )
            print(f"scoped {user.email} to VIP {scope.vip_id} (reveal={scope.can_reveal_sensitive})")
        elif args.command == "grant-reveal":
            user = service.get_user_by_email(args.email)
            scope = service.grant_reveal(user.id, uuid.UUID(args.vip_id))
            print(f"reveal granted to {user.email} for VIP {scope.vip_id}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    configure_logging()
    args = build_parser().parse_args(argv)
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
