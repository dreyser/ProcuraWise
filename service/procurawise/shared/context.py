from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, HTTPException


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


def require_role(*roles: str) -> Callable[..., ActorContext]:
    """Dependency factory: 403s if the resolved actor's role is not one of
    `roles`. No such dependency existed before VS-2B - identity's own routes
    (`/me`, `/dev/actors`) never needed per-role gating. The import of
    `get_current_context` is deferred to call time (not module load time) to
    avoid a circular import: `identity.dev_provider` itself imports
    `ActorContext` from this module."""

    def _dependency(context: ActorContext) -> ActorContext:
        if context.role not in roles:
            raise HTTPException(status_code=403, detail="role not permitted")
        return context

    from procurawise.identity.dev_provider import get_current_context

    def _require_role(context: ActorContext = Depends(get_current_context)) -> ActorContext:
        return _dependency(context)

    return _require_role
