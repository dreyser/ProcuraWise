from procurawise.shared.api_models import APIModel


class DevActorSummary(APIModel):
    """One selectable development actor for the `/dev` picker. `actor_id` is
    an alias for the underlying Membership id - selecting an actor means
    selecting a Membership, not a user."""

    actor_id: str
    display_name: str
    tenant_name: str
    role: str
    vendor_org_id: str | None = None


class ActorContextResponse(APIModel):
    membership_id: str
    user_id: str
    tenant_id: str
    tenant_name: str
    role: str
    vendor_org_id: str | None = None
    display_name: str


class VendorOrganizationSummary(APIModel):
    """Deliberately minimal: no tenant_id, no created_at - this is a picker
    catalog, not the full VendorOrganization record."""

    id: str
    name: str


class VendorOrganizationListResponse(APIModel):
    items: list[VendorOrganizationSummary]
    next_cursor: str | None = None


class OrgMemberSummary(APIModel):
    """One Membership within the caller's own tenant (spec §4:
    "Administrador del cliente: Usuarios, roles..."). Never cross-tenant -
    that's platform_admin's `find_across_tenants()` escape hatch, a
    structurally different, physically separate mechanism (procurawise.admin)."""

    membership_id: str
    user_id: str
    email: str
    display_name: str
    role: str
    vendor_org_id: str | None = None


class OrgMembersListResponse(APIModel):
    items: list[OrgMemberSummary]
