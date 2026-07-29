from procurawise.identity.schemas import ActorContextResponse
from procurawise.shared.api_models import APIModel


class LoginRequest(APIModel):
    email: str
    password: str


class PreSessionResponse(APIModel):
    """Issued by POST /auth/login (and, from Bloque 3, the OIDC callback) -
    proves "this is a real user", nothing about tenant/role yet."""

    pre_session_token: str
    token_type: str = "bearer"
    expires_in: int


class MembershipOption(APIModel):
    membership_id: str
    tenant_id: str
    tenant_name: str
    role: str
    display_name: str


class MembershipsResponse(APIModel):
    memberships: list[MembershipOption]


class SwitchTenantRequest(APIModel):
    membership_id: str


class TokenResponse(APIModel):
    """The final access token, scoped to exactly one tenant/role - "one JWT =
    one tenant" (ADR 0002)."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    actor: ActorContextResponse
