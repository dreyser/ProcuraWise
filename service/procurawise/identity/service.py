import base64
import json

from procurawise.identity.models import Membership, VendorOrganization
from procurawise.identity.repository import (
    MembershipRepository,
    TenantRepository,
    UserRepository,
    VendorOrganizationRepository,
)
from procurawise.shared.context import ActorContext


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

    def list_dev_actors(self) -> list[ActorContext]:
        contexts = (
            self._build_context(Membership.from_document(doc))
            for doc in self._memberships.list_all_for_dev()
        )
        return [context for context in contexts if context is not None]

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
