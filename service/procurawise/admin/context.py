from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

from procurawise.identity.jwt_provider import (
    ADMIN_ACCESS_TOKEN_USE,
    TokenError,
    decode_token,
    extract_bearer_token,
)
from procurawise.shared.config import Settings, get_settings


@dataclass(frozen=True)
class PlatformAdminContext:
    """The resolved identity of an authenticated platform_admin caller.
    Deliberately NOT `shared.context.ActorContext` - that dataclass requires
    a `tenant_id`, which platform_admin structurally does not have
    (architecture.md §5). Every `/api/v1/admin/*` route depends on this
    instead, never on ActorContext."""

    admin_id: str
    display_name: str
    role: str = "platform_admin"


def get_current_admin_context(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> PlatformAdminContext:
    token = extract_bearer_token(authorization)
    try:
        claims = decode_token(token, settings, expected_use=ADMIN_ACCESS_TOKEN_USE)
    except TokenError:
        raise HTTPException(status_code=401, detail="invalid or expired token") from None
    return PlatformAdminContext(
        admin_id=claims["admin_id"],
        display_name=claims["display_name"],
    )


def require_platform_admin() -> Callable[..., PlatformAdminContext]:
    """Trivial today (there is only one possible caller identity for
    `/api/v1/admin/*`), kept as a factory - not a bare Depends(...) alias -
    so every admin route reads the same way require_role(...) does on buyer
    routers, and so a second admin-side role could be added later without
    changing call sites."""

    def _require_platform_admin(
        context: PlatformAdminContext = Depends(get_current_admin_context),
    ) -> PlatformAdminContext:
        return context

    return _require_platform_admin
