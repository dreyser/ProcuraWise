from procurawise.identity.models import Membership
from procurawise.identity.repository import MembershipRepository, TenantRepository, UserRepository
from procurawise.shared.context import ActorContext


class ActorNotFoundError(Exception):
    """No Membership (or its Tenant/User) exists for a given membership_id."""


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
