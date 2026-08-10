from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from procurawise.identity.auth_schemas import (
    LoginRequest,
    MembershipOption,
    MembershipsResponse,
    PreSessionResponse,
    SwitchTenantRequest,
    TokenResponse,
)
from procurawise.identity.jwt_provider import (
    TokenError,
    create_access_token,
    create_oidc_state_token,
    create_pre_session_token,
    decode_oidc_state_token,
    get_authenticated_user_id,
)
from procurawise.identity.models import OidcIdentity, OidcProviderName, User
from procurawise.identity.oidc import (
    AuthlibOidcProvider,
    OidcConfigurationError,
    OidcExchangeError,
    OidcProvider,
)
from procurawise.identity.passwords import verify_password
from procurawise.identity.repository import UserRepository
from procurawise.identity.schemas import ActorContextResponse
from procurawise.identity.service import ActorNotFoundError, IdentityService, get_identity_service
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.mongo import get_database
from procurawise.shared.rate_limit import enforce_login_not_locked_out, record_login_failure
from procurawise.shared.request_ip import resolve_client_ip
from procurawise.shared.roles import BUYER_LOGIN_ROLES

router = APIRouter(prefix="/auth", tags=["auth"])

# Only buyer roles ever get a real access token through this router -
# vendor_contact stays on the interim mechanism (AUTH-PROD scope decision #1,
# see vendor_portal/router.py); platform_admin has no tenant_id claim and
# isn't a Membership at all (see procurawise.admin, Fase 9 Block 4). Enforced
# twice, independently: memberships() filters the list a user is even
# offered, switch_tenant() re-checks the chosen membership's role
# server-side before minting a token - a client skipping straight to
# switch-tenant with a guessed vendor membership_id still gets rejected.
BUYER_ROLES: tuple[str, ...] = BUYER_LOGIN_ROLES


def get_user_repository(settings: Settings = Depends(get_settings)) -> UserRepository:
    return UserRepository(get_database(settings))


def get_oidc_provider(
    provider: OidcProviderName, settings: Settings = Depends(get_settings)
) -> OidcProvider:
    """`provider` is resolved from the route's own path parameter of the same
    name - FastAPI shares path params across a request's whole dependency
    tree, not just the endpoint function itself. Overridden in tests via
    `app.dependency_overrides` with a fake that returns canned claims, so
    automated tests never need a real Microsoft/Google OAuth app or network
    access (see tests/fakes/fake_oidc_provider.py)."""
    try:
        return AuthlibOidcProvider(provider, settings)
    except OidcConfigurationError:
        raise HTTPException(status_code=503, detail="oidc provider not configured") from None


@router.post("/login", response_model=PreSessionResponse)
def login(
    body: LoginRequest,
    request: Request,
    users: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
) -> PreSessionResponse:
    # Fase 26 (Hardening, plan Bloque 2): brute-force mitigation, keyed by
    # (IP, email) - not IP alone (a blanket per-IP counter would also block
    # legitimate rapid logins into many *different* accounts from the same
    # network) - and only failed attempts count toward lockout, checked
    # here before the credential check and recorded only in the failure
    # branch below. A successful login never counts against the same
    # account's own budget - this app's own E2E suite logs the same small,
    # fixed roster of dev-seeded accounts in successfully dozens of times
    # across its 18 specs, which a "every request counts" limiter would
    # have wrongly throttled.
    ip = resolve_client_ip(request, settings)
    login_rate_limit_key = f"login:{ip}:{body.email}"
    enforce_login_not_locked_out(
        login_rate_limit_key,
        settings.rate_limit_login_max_attempts,
        settings.rate_limit_login_window_seconds,
    )

    doc = users.find_by_email(body.email)
    user = User.from_document(doc) if doc is not None else None
    # Never distinguish "no such email" / "OIDC-only account, no password
    # set" / "wrong password" in the response - all three collapse to the
    # same generic 401, so a caller can't use this endpoint to enumerate
    # which emails have an account.
    if (
        user is None
        or user.password_hash is None
        or not verify_password(body.password, user.password_hash)
    ):
        record_login_failure(login_rate_limit_key, settings.rate_limit_login_window_seconds)
        raise HTTPException(status_code=401, detail="invalid credentials")

    token, expires_in = create_pre_session_token(user.id, settings)
    return PreSessionResponse(pre_session_token=token, expires_in=expires_in)


@router.get("/memberships", response_model=MembershipsResponse)
def list_memberships(
    user_id: str = Depends(get_authenticated_user_id),
    identity_service: IdentityService = Depends(get_identity_service),
) -> MembershipsResponse:
    contexts = identity_service.list_memberships_for_user(user_id, roles=BUYER_ROLES)
    return MembershipsResponse(
        memberships=[
            MembershipOption(
                membership_id=context.membership_id,
                tenant_id=context.tenant_id,
                tenant_name=context.tenant_name,
                role=context.role,
                display_name=context.display_name,
            )
            for context in contexts
        ]
    )


@router.post("/switch-tenant", response_model=TokenResponse)
def switch_tenant(
    body: SwitchTenantRequest,
    user_id: str = Depends(get_authenticated_user_id),
    identity_service: IdentityService = Depends(get_identity_service),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    try:
        context = identity_service.resolve_actor_context(body.membership_id)
    except ActorNotFoundError:
        raise HTTPException(status_code=403, detail="membership not permitted") from None
    # Same generic 403 for "doesn't exist", "belongs to someone else", and
    # "exists but is a vendor_contact membership" - never distinguished, so
    # this endpoint can't be used to probe for other users' membership ids.
    if context.user_id != user_id or context.role not in BUYER_ROLES:
        raise HTTPException(status_code=403, detail="membership not permitted")

    access_token, expires_in = create_access_token(context, settings)
    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        actor=ActorContextResponse(
            membership_id=context.membership_id,
            user_id=context.user_id,
            tenant_id=context.tenant_id,
            tenant_name=context.tenant_name,
            role=context.role,
            vendor_org_id=context.vendor_org_id,
            display_name=context.display_name,
        ),
    )


@router.get("/oidc/{provider}/login")
def oidc_login(
    provider: OidcProviderName,
    settings: Settings = Depends(get_settings),
    oidc: OidcProvider = Depends(get_oidc_provider),
) -> RedirectResponse:
    state, nonce = create_oidc_state_token(settings)
    return RedirectResponse(
        oidc.authorization_redirect_url(state=state, nonce=nonce), status_code=302
    )


@router.get("/oidc/{provider}/callback")
async def oidc_callback(
    provider: OidcProviderName,
    code: str,
    state: str,
    settings: Settings = Depends(get_settings),
    oidc: OidcProvider = Depends(get_oidc_provider),
    users: UserRepository = Depends(get_user_repository),
) -> RedirectResponse:
    try:
        nonce = decode_oidc_state_token(state, settings)
    except TokenError:
        raise HTTPException(status_code=400, detail="invalid or expired oidc state") from None

    try:
        claims = await oidc.exchange_code(code=code, nonce=nonce)
    except OidcExchangeError:
        raise HTTPException(status_code=401, detail="oidc exchange failed") from None

    doc = users.find_by_email(claims.email)
    if doc is None:
        # The IdP really did authenticate this person - ProcuraWise simply
        # has no account for them (AUTH-PROD has no self-signup). 403, not
        # 401: they proved who they are, they're just not provisioned.
        raise HTTPException(status_code=403, detail="account not provisioned")
    user = User.from_document(doc)

    already_linked = any(
        identity.provider == provider and identity.subject == claims.subject
        for identity in user.oidc_identities
    )
    if not already_linked:
        if not claims.email_verified:
            raise HTTPException(status_code=403, detail="email not verified by provider")
        # Just-in-time link by verified email: the User already exists via
        # administrative provisioning (provisioning_cli.py/dev_seed.py), this
        # only records that its owner has now proven control of that email
        # through this provider too.
        linked = user.with_oidc_identity(
            OidcIdentity(provider=provider, subject=claims.subject, linked_at=datetime.now(UTC))
        )
        users.update_oidc_identities(
            user.id, [identity.to_document() for identity in linked.oidc_identities]
        )

    token, expires_in = create_pre_session_token(user.id, settings)
    return RedirectResponse(
        f"{settings.frontend_base_url}/auth/callback"
        f"#pre_session_token={token}&expires_in={expires_in}",
        status_code=302,
    )
