import secrets
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from fastapi import Depends, Header, HTTPException

from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext

TokenUse = Literal["access", "pre_session", "oidc_state", "admin_access"]

ACCESS_TOKEN_USE: TokenUse = "access"
PRE_SESSION_TOKEN_USE: TokenUse = "pre_session"
OIDC_STATE_TOKEN_USE: TokenUse = "oidc_state"
ADMIN_ACCESS_TOKEN_USE: TokenUse = "admin_access"
OIDC_STATE_TTL_MINUTES = 2


class TokenError(Exception):
    """Base for any token that must be rejected - never distinguished to the
    HTTP caller beyond a generic 401, to avoid giving an attacker a signal
    about *why* their token was rejected."""


class TokenExpiredError(TokenError):
    pass


class TokenInvalidError(TokenError):
    """Malformed, badly signed, or carrying the wrong `token_use` (e.g. a
    pre-session token presented where an access token is required)."""


def _issue(payload: dict[str, Any], ttl_minutes: int, settings: Settings) -> tuple[str, int]:
    ttl_seconds = ttl_minutes * 60
    now = datetime.now(UTC)
    full_payload = {
        **payload,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    token = jwt.encode(full_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, ttl_seconds


def create_access_token(context: ActorContext, settings: Settings) -> tuple[str, int]:
    """The access token embeds every ActorContext field directly ("fat JWT") -
    a verified request never round-trips to Mongo to resolve identity, unlike
    the dev-header mechanism it replaces for buyer routes. The tradeoff is a
    membership/role change only takes effect on next login/switch-tenant, not
    mid-session - acceptable given the short TTL and no-refresh design
    (AUTH-PROD scope decision #2)."""
    payload = {**asdict(context), "sub": context.user_id, "token_use": ACCESS_TOKEN_USE}
    return _issue(payload, settings.access_token_ttl_minutes, settings)


def create_admin_access_token(
    admin_id: str, display_name: str, settings: Settings
) -> tuple[str, int]:
    """`platform_admin` has no tenant_id claim at all (architecture.md §5) -
    a distinct `token_use` (not ACCESS_TOKEN_USE) means this token is
    structurally rejected by identity.jwt_provider.get_current_context (the
    dependency every buyer router's require_role resolves through), not just
    role-checked away. A platform_admin JWT can never be mistaken for, or
    accidentally accepted as, a buyer ActorContext (Fase 9 Block 4)."""
    payload = {
        "sub": admin_id,
        "admin_id": admin_id,
        "display_name": display_name,
        "token_use": ADMIN_ACCESS_TOKEN_USE,
    }
    return _issue(payload, settings.access_token_ttl_minutes, settings)


def create_pre_session_token(user_id: str, settings: Settings) -> tuple[str, int]:
    """Issued right after login/OIDC callback, before a tenant is chosen -
    proves "this is user_id", nothing about role/tenant yet. Exchanged for an
    access token via POST /auth/switch-tenant."""
    payload = {"sub": user_id, "token_use": PRE_SESSION_TOKEN_USE}
    return _issue(payload, settings.pre_session_token_ttl_minutes, settings)


def create_oidc_state_token(settings: Settings) -> tuple[str, str]:
    """OAuth `state` (CSRF) and OIDC `nonce` (id_token replay) folded into one
    signed, short-lived JWT instead of server-side session storage - there is
    no session store in this design (scope decision #2). The nonce is
    embedded as a claim inside the very token used as `state`, so the
    callback can recover it (decode_oidc_state_token) without anything else
    to persist between the login and callback requests."""
    nonce = secrets.token_urlsafe(16)
    payload = {"token_use": OIDC_STATE_TOKEN_USE, "nonce": nonce}
    token, _ = _issue(payload, OIDC_STATE_TTL_MINUTES, settings)
    return token, nonce


def decode_oidc_state_token(token: str, settings: Settings) -> str:
    """Returns the nonce embedded in a state token created by
    create_oidc_state_token, after verifying its signature/expiry/token_use."""
    claims = decode_token(token, settings, expected_use=OIDC_STATE_TOKEN_USE)
    return str(claims["nonce"])


def _decode(token: str, settings: Settings) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError() from None
    except jwt.InvalidTokenError:
        raise TokenInvalidError() from None


def decode_token(token: str, settings: Settings, *, expected_use: TokenUse) -> dict[str, Any]:
    claims = _decode(token, settings)
    if claims.get("token_use") != expected_use:
        raise TokenInvalidError()
    return claims


def extract_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    return authorization[len("bearer ") :].strip()


def get_current_context(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> ActorContext:
    """Production identity dependency for buyer routes (evaluation_owner/
    evaluator) - reads `Authorization: Bearer <access token>`, verifies it,
    and builds ActorContext directly from its claims (no Mongo round-trip,
    see create_access_token). Wired into shared.context.require_role in place
    of identity.dev_provider.get_current_context (AUTH-PROD)."""
    token = extract_bearer_token(authorization)
    try:
        claims = decode_token(token, settings, expected_use=ACCESS_TOKEN_USE)
    except TokenError:
        raise HTTPException(status_code=401, detail="invalid or expired token") from None
    return ActorContext(
        membership_id=claims["membership_id"],
        user_id=claims["user_id"],
        tenant_id=claims["tenant_id"],
        tenant_name=claims["tenant_name"],
        role=claims["role"],
        vendor_org_id=claims.get("vendor_org_id"),
        display_name=claims["display_name"],
    )


def get_authenticated_user_id(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> str:
    """Accepts either a pre-session token (issued right after login/OIDC,
    before a tenant is chosen) or a full access token - both prove "this is
    user_id", which is all GET /auth/memberships and POST /auth/switch-tenant
    need. Deliberately does not build an ActorContext: there may be no tenant
    resolved yet."""
    token = extract_bearer_token(authorization)
    try:
        claims = _decode(token, settings)
    except TokenError:
        raise HTTPException(status_code=401, detail="invalid or expired token") from None
    if claims.get("token_use") not in (ACCESS_TOKEN_USE, PRE_SESSION_TOKEN_USE):
        raise HTTPException(status_code=401, detail="invalid or expired token")
    return str(claims["sub"])
