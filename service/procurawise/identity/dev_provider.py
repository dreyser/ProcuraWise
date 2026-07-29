from fastapi import Depends, Header, HTTPException

from procurawise.identity.service import ActorNotFoundError, IdentityService, get_identity_service
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext

# The dev/test-only selector: the client sends the id of a *Membership*, never
# a user_id, tenant_id, or role - the Membership row is the sole source of
# truth for tenant/role/vendor binding, resolved entirely server-side. Kept as
# the vendor_contact identity mechanism after AUTH-PROD (scope decision #1) -
# buyer routes resolve identity via identity.jwt_provider instead.
DEV_ACTOR_HEADER = "X-Dev-Membership-Id"


def require_dev_environment(settings: Settings) -> None:
    if settings.environment not in ("local", "test"):
        # 404, not 403: outside development/test this mechanism must not even
        # appear to exist.
        raise HTTPException(status_code=404)


def get_current_context(
    settings: Settings = Depends(get_settings),
    identity_service: IdentityService = Depends(get_identity_service),
    x_dev_membership_id: str | None = Header(default=None, alias=DEV_ACTOR_HEADER),
) -> ActorContext:
    require_dev_environment(settings)
    if not x_dev_membership_id:
        raise HTTPException(status_code=401, detail=f"missing {DEV_ACTOR_HEADER} header")
    try:
        return identity_service.resolve_actor_context(x_dev_membership_id)
    except ActorNotFoundError:
        raise HTTPException(status_code=401, detail="unknown development actor") from None
