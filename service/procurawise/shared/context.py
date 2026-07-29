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
    `roles`. Used by every buyer router (evaluations/proposals/scoring/
    identity) - resolves identity via identity.jwt_provider.get_current_context
    (AUTH-PROD's real JWT, ADR 0003), swapped in from
    identity.dev_provider.get_current_context (the dev-header mechanism) with
    no change required to any of those routers, exactly as this module's
    ActorContext docstring above promised.

    vendor_portal deliberately does NOT use this factory (AUTH-PROD scope
    decision #1: vendor_contact stays on the interim dev-header mechanism
    until Fase 15) - it builds its own dependency directly against
    identity.dev_provider.get_current_context instead, see
    vendor_portal/router.py.

    The import is deferred to call time (not module load time) to avoid a
    circular import: identity.jwt_provider itself imports ActorContext from
    this module."""

    def _dependency(context: ActorContext) -> ActorContext:
        if context.role not in roles:
            raise HTTPException(status_code=403, detail="role not permitted")
        return context

    from procurawise.identity.jwt_provider import get_current_context

    def _require_role(context: ActorContext = Depends(get_current_context)) -> ActorContext:
        return _dependency(context)

    return _require_role
