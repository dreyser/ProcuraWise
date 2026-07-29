"""Administrative CLI to provision a real buyer Tenant+User+Membership.

AUTH-PROD deliberately has no self-signup endpoint (scope decision #3): a
buyer account can only be created this way, by whoever has direct access to
the deployment (SSH/exec into the container), never over HTTP. Runs in any
environment, including production - unlike dev_seed.py, which is gated to
local/test.
"""

import argparse
import getpass
import sys

from procurawise.identity.models import Membership, Role, Tenant, User
from procurawise.identity.passwords import hash_password
from procurawise.identity.repository import MembershipRepository, TenantRepository, UserRepository
from procurawise.shared.config import get_settings
from procurawise.shared.logging import configure_logging
from procurawise.shared.mongo import get_database

BUYER_ROLES: tuple[Role, ...] = ("evaluation_owner", "evaluator")


def _get_or_create_tenant(tenants: TenantRepository, slug: str, name: str) -> Tenant:
    existing = tenants.find_by_slug(slug)
    if existing is not None:
        return Tenant.from_document(existing)
    tenant = Tenant.create(slug=slug, name=name)
    tenants.insert(tenant.to_document())
    return tenant


def _get_or_create_user(
    users: UserRepository, email: str, display_name: str, password: str | None
) -> User:
    existing = users.find_by_email(email)
    if existing is not None:
        return User.from_document(existing)
    password_hash = hash_password(password) if password else None
    user = User.create(display_name=display_name, email=email, password_hash=password_hash)
    users.insert(user.to_document())
    return user


def provision(
    *,
    tenant_slug: str,
    tenant_name: str,
    email: str,
    display_name: str,
    role: Role,
    password: str | None,
) -> Membership:
    if role not in BUYER_ROLES:
        raise ValueError(f"role must be one of {BUYER_ROLES}, got {role!r}")

    settings = get_settings()
    db = get_database(settings)
    tenants = TenantRepository(db)
    users = UserRepository(db)
    memberships = MembershipRepository(db)

    tenant = _get_or_create_tenant(tenants, tenant_slug, tenant_name)
    user = _get_or_create_user(users, email, display_name, password)

    existing_membership = memberships.find_one_for(tenant.id, user.id, role, None)
    if existing_membership is not None:
        return Membership.from_document(existing_membership)

    membership = Membership.create(tenant_id=tenant.id, user_id=user.id, role=role)
    memberships.insert(membership.to_document())
    return membership


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Provision a real buyer Tenant+User+Membership. No HTTP endpoint "
            "exists for this (AUTH-PROD has no self-signup) - this CLI is the "
            "only way to create a real buyer account."
        )
    )
    parser.add_argument("--tenant-slug", required=True)
    parser.add_argument("--tenant-name", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--role", choices=BUYER_ROLES, default="evaluation_owner")
    parser.add_argument(
        "--no-password",
        action="store_true",
        help="OIDC-only user: no local password is set, login only via Microsoft/Google.",
    )
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings)

    password: str | None = None
    if not args.no_password:
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("passwords do not match", file=sys.stderr)
            sys.exit(1)

    membership = provision(
        tenant_slug=args.tenant_slug,
        tenant_name=args.tenant_name,
        email=args.email,
        display_name=args.display_name,
        role=args.role,
        password=password,
    )
    print(f"membership_id={membership.id} tenant_id={membership.tenant_id} role={membership.role}")


if __name__ == "__main__":
    main()
