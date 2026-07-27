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
