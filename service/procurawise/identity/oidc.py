from dataclasses import dataclass
from typing import Protocol

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
from joserfc import jwt as jose_jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet
from joserfc.jwt import JWTClaimsRegistry

from procurawise.identity.models import OidcProviderName
from procurawise.shared.config import Settings


@dataclass(frozen=True)
class OidcIdentityClaims:
    email: str
    subject: str
    email_verified: bool


class OidcConfigurationError(Exception):
    """The requested provider has no client_id/client_secret configured
    (always true outside production by default - see Settings)."""


class OidcExchangeError(Exception):
    """The authorization code could not be exchanged, or the returned
    id_token failed signature/audience/nonce/issuer validation. Never
    distinguished further to the HTTP caller (generic 401), same principle as
    jwt_provider.TokenError."""


class OidcProvider(Protocol):
    def authorization_redirect_url(self, *, state: str, nonce: str) -> str: ...

    async def exchange_code(self, *, code: str, nonce: str) -> OidcIdentityClaims: ...


def _microsoft_endpoints(tenant: str) -> dict[str, str]:
    base = f"https://login.microsoftonline.com/{tenant}"
    return {
        "authorize": f"{base}/oauth2/v2.0/authorize",
        "token": f"{base}/oauth2/v2.0/token",
        "jwks": f"{base}/discovery/v2.0/keys",
    }


_GOOGLE_ENDPOINTS = {
    "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
    "token": "https://oauth2.googleapis.com/token",
    "jwks": "https://www.googleapis.com/oauth2/v3/certs",
    "issuer": "https://accounts.google.com",
}


class AuthlibOidcProvider:
    """Real OIDC authorization-code client (ADR 0003), built directly on
    authlib's low-level httpx OAuth2 client rather than
    authlib.integrations.starlette_client.OAuth - that integration expects
    Starlette's SessionMiddleware/cookies to carry flow state, which
    AUTH-PROD deliberately doesn't use (scope decision #2: no cookies, no
    server-side session). State/nonce instead round-trip inside a signed JWT
    (jwt_provider.create_oidc_state_token/decode_oidc_state_token).

    Endpoints are hardcoded per provider rather than resolved from each
    IdP's `.well-known/openid-configuration` - both providers' endpoints are
    stable, documented, versioned URLs; a discovery round trip would be an
    extra network call and failure mode for no real benefit here."""

    def __init__(self, provider_name: OidcProviderName, settings: Settings) -> None:
        self._provider_name = provider_name
        self._settings = settings
        if provider_name == "microsoft":
            if not settings.oidc_microsoft_client_id or not settings.oidc_microsoft_client_secret:
                raise OidcConfigurationError(provider_name)
            self._client_id = settings.oidc_microsoft_client_id
            self._client_secret = settings.oidc_microsoft_client_secret
            self._endpoints = _microsoft_endpoints(settings.oidc_microsoft_tenant)
        else:
            if not settings.oidc_google_client_id or not settings.oidc_google_client_secret:
                raise OidcConfigurationError(provider_name)
            self._client_id = settings.oidc_google_client_id
            self._client_secret = settings.oidc_google_client_secret
            self._endpoints = _GOOGLE_ENDPOINTS

    @property
    def _redirect_uri(self) -> str:
        return (
            f"{self._settings.oidc_redirect_base_url}"
            f"/api/v1/auth/oidc/{self._provider_name}/callback"
        )

    def authorization_redirect_url(self, *, state: str, nonce: str) -> str:
        client = AsyncOAuth2Client(
            client_id=self._client_id, redirect_uri=self._redirect_uri, scope="openid email profile"
        )
        url, _state = client.create_authorization_url(
            self._endpoints["authorize"], state=state, nonce=nonce, response_mode="query"
        )
        return str(url)

    async def exchange_code(self, *, code: str, nonce: str) -> OidcIdentityClaims:
        client = AsyncOAuth2Client(
            client_id=self._client_id,
            client_secret=self._client_secret,
            redirect_uri=self._redirect_uri,
        )
        try:
            token = await client.fetch_token(self._endpoints["token"], code=code)
        except Exception as exc:
            raise OidcExchangeError("token exchange failed") from exc

        id_token = token.get("id_token")
        if not id_token:
            raise OidcExchangeError("no id_token in token response")

        async with httpx.AsyncClient(timeout=5.0) as http_client:
            jwks_response = await http_client.get(self._endpoints["jwks"])
            jwks_response.raise_for_status()
            key_set = KeySet.import_key_set(jwks_response.json())

        try:
            token = jose_jwt.decode(id_token, key_set, algorithms=["RS256"])
            JWTClaimsRegistry(exp={"essential": True}).validate(token.claims)
        except JoseError as exc:
            raise OidcExchangeError("invalid id_token") from exc

        claims = token.claims
        if claims.get("aud") != self._client_id:
            raise OidcExchangeError("id_token audience mismatch")
        if claims.get("nonce") != nonce:
            raise OidcExchangeError("id_token nonce mismatch")
        if self._provider_name == "google" and claims.get("iss") != _GOOGLE_ENDPOINTS["issuer"]:
            raise OidcExchangeError("id_token issuer mismatch")

        email = claims.get("email")
        if not email:
            raise OidcExchangeError("id_token has no email claim")

        return OidcIdentityClaims(
            email=email,
            subject=str(claims["sub"]),
            email_verified=bool(claims.get("email_verified", False)),
        )
