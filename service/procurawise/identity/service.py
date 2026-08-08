import base64
import json
from typing import Any

from fastapi import Depends

from procurawise.identity.models import Membership, VendorOrganization
from procurawise.identity.repository import (
    MembershipRepository,
    TenantRepository,
    UserRepository,
    VendorOrganizationRepository,
)
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext
from procurawise.shared.mongo import get_database


class ActorNotFoundError(Exception):
    """No Membership (or its Tenant/User) exists for a given membership_id."""


class InvalidVendorOrganizationCursorError(Exception):
    """The `cursor` query param is not a value this endpoint produced."""


class IdentityService:
    def __init__(
        self,
        tenants: TenantRepository,
        users: UserRepository,
        memberships: MembershipRepository,
    ) -> None:
        self._tenants = tenants
        self._users = users
        self._memberships = memberships

    def resolve_actor_context(self, membership_id: str) -> ActorContext:
        doc = self._memberships.find_by_id(membership_id)
        if doc is None:
            raise ActorNotFoundError(membership_id)
        context = self._build_context(Membership.from_document(doc))
        if context is None:
            raise ActorNotFoundError(membership_id)
        return context

    def resolve_recipient_email(self, membership_id: str) -> tuple[str, str] | None:
        """Fase 24 (notifications): (email, display_name) for a Membership's
        underlying User - ActorContext deliberately carries no email field
        (it's the resolved-identity shape every buyer/vendor router already
        depends on, no need to widen it for one new consumer), so this is a
        narrow, separate lookup rather than a field added to
        resolve_actor_context. Returns None (never raises) if the Membership
        or its User no longer resolves - same "skip, don't crash" contract
        callers already get from resolve_actor_context raising
        ActorNotFoundError, just shaped for a caller (NotificationService)
        that treats a missing recipient as "nothing to send", not an error."""
        doc = self._memberships.find_by_id(membership_id)
        if doc is None:
            return None
        membership = Membership.from_document(doc)
        user_doc = self._users.find_by_id(membership.user_id)
        if user_doc is None:
            return None
        return user_doc["email"], user_doc["display_name"]

    def list_dev_actors(self) -> list[ActorContext]:
        contexts = (
            self._build_context(Membership.from_document(doc))
            for doc in self._memberships.list_all_for_dev()
        )
        return [context for context in contexts if context is not None]

    def list_memberships_for_user(
        self, user_id: str, *, roles: tuple[str, ...]
    ) -> list[ActorContext]:
        """Used by AUTH-PROD's GET /auth/memberships: every Membership the
        authenticated user holds, filtered to `roles` (buyer roles only, in
        practice - defense in depth against a vendor_contact Membership ever
        being offered through the buyer login flow, see auth_router.py)."""
        contexts = (
            self._build_context(Membership.from_document(doc))
            for doc in self._memberships.find_all_for_user(user_id)
        )
        return [context for context in contexts if context is not None and context.role in roles]

    def list_members_for_tenant(self, tenant_id: str) -> list[dict[str, Any]]:
        """Backs `tenant_admin`'s "Usuarios, roles" capability (spec §4) -
        every Membership within the caller's own tenant, joined with the
        owning User's email/display_name. Deliberately tenant-scoped, unlike
        `procurawise.admin`'s cross-tenant escape hatch."""
        members = []
        for doc in self._memberships.find_all_for_tenant(tenant_id):
            membership = Membership.from_document(doc)
            user_doc = self._users.find_by_id(membership.user_id)
            members.append(
                {
                    "membership_id": membership.id,
                    "user_id": membership.user_id,
                    "email": user_doc["email"] if user_doc else membership.user_id,
                    "display_name": user_doc["display_name"] if user_doc else membership.user_id,
                    "role": membership.role,
                    "vendor_org_id": membership.vendor_org_id,
                }
            )
        return members

    def _build_context(self, membership: Membership) -> ActorContext | None:
        tenant_doc = self._tenants.find_by_id(membership.tenant_id)
        user_doc = self._users.find_by_id(membership.user_id)
        if tenant_doc is None or user_doc is None:
            return None
        return ActorContext(
            membership_id=membership.id,
            user_id=membership.user_id,
            tenant_id=membership.tenant_id,
            tenant_name=tenant_doc["name"],
            role=membership.role,
            vendor_org_id=membership.vendor_org_id,
            display_name=user_doc["display_name"],
        )


def get_identity_service(settings: Settings = Depends(get_settings)) -> IdentityService:
    """Shared factory - used by the dev-header provider (identity/dev_provider.py,
    still the vendor_contact mechanism) and by AUTH-PROD's identity/auth_router.py
    alike. Lives here, not in either of those, since both depend on it rather
    than on each other."""
    db = get_database(settings)
    return IdentityService(
        tenants=TenantRepository(db),
        users=UserRepository(db),
        memberships=MembershipRepository(db),
    )


def _encode_vendor_organization_cursor(name: str, vendor_org_id: str) -> str:
    payload = json.dumps([name, vendor_org_id]).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def _decode_vendor_organization_cursor(cursor: str) -> tuple[str, str]:
    try:
        payload = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        data = json.loads(payload)
        if (
            not isinstance(data, list)
            or len(data) != 2
            or not all(isinstance(part, str) for part in data)
        ):
            raise ValueError("malformed cursor payload")
    except Exception as exc:
        raise InvalidVendorOrganizationCursorError(cursor) from exc
    return data[0], data[1]


class VendorOrganizationService:
    """Read-only, tenant-scoped catalog backing the "link vendor" picker
    (VS-2C gap - see docs/development/current-phase.md). Deliberately
    separate from IdentityService: that one resolves dev-actor identity,
    this one lists tenant-owned business data."""

    def __init__(self, vendor_orgs: VendorOrganizationRepository) -> None:
        self._vendor_orgs = vendor_orgs

    def list_vendor_organizations(
        self, tenant_id: str, *, search: str | None, limit: int, cursor: str | None
    ) -> tuple[list[VendorOrganization], str | None]:
        decoded_cursor = _decode_vendor_organization_cursor(cursor) if cursor else None
        docs = self._vendor_orgs.find_many(
            tenant_id, search=search, limit=limit, cursor=decoded_cursor
        )
        organizations = [VendorOrganization.from_document(doc) for doc in docs[:limit]]
        next_cursor = (
            _encode_vendor_organization_cursor(organizations[-1].name, organizations[-1].id)
            if len(docs) > limit
            else None
        )
        return organizations, next_cursor
