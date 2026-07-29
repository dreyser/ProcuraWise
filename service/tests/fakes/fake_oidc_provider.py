from dataclasses import dataclass

from procurawise.identity.oidc import OidcIdentityClaims


@dataclass
class FakeOidcProvider:
    """Test double for identity.oidc.OidcProvider - returns canned claims
    instead of talking to a real IdP, so tests/api/test_auth_router.py can
    exercise the full login -> callback -> pre-session-token flow with zero
    network calls and zero real Microsoft/Google OAuth app registrations
    (AUTH-PROD Bloque 3). Overridden in per-test via
    `app.dependency_overrides[get_oidc_provider]`."""

    claims: OidcIdentityClaims
    authorize_base_url: str = "https://idp.example.test/authorize"

    def authorization_redirect_url(self, *, state: str, nonce: str) -> str:
        return f"{self.authorize_base_url}?state={state}&nonce={nonce}"

    async def exchange_code(self, *, code: str, nonce: str) -> OidcIdentityClaims:
        return self.claims
