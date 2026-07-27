from dataclasses import dataclass


@dataclass(frozen=True)
class ActorContext:
    """The resolved identity of the caller for the current request: which
    Membership was selected, and the tenant/role/vendor binding it carries.
    Produced today by `identity.dev_provider.DevelopmentIdentityProvider`;
    a future JWT-based provider must produce the exact same shape so routers
    and services never need to change when auth becomes real (see ADR 0003)."""

    membership_id: str
    user_id: str
    tenant_id: str
    tenant_name: str
    role: str
    vendor_org_id: str | None
    display_name: str
