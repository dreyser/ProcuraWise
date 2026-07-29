from urllib.parse import parse_qs, urlsplit

import pytest

from procurawise.api.main import app
from procurawise.dev_seed import DEV_BUYER_PASSWORD
from procurawise.identity.auth_router import get_oidc_provider
from procurawise.identity.models import Membership, User, VendorOrganization
from procurawise.identity.oidc import OidcIdentityClaims
from procurawise.identity.repository import (
    MembershipRepository,
    UserRepository,
    VendorOrganizationRepository,
)
from tests.conftest import unique_actor_by_role
from tests.fakes.fake_oidc_provider import FakeOidcProvider

pytestmark = pytest.mark.docker


def _login(client, email: str, password: str = DEV_BUYER_PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _pre_session_token(client, email: str) -> str:
    response = _login(client, email)
    assert response.status_code == 200
    return response.json()["pre_session_token"]


def _membership_id_for(mongo_test_db, email: str, role: str) -> str:
    """Resolves a Membership id by (email, role) directly against Mongo -
    tenant_ids()'s tenant_a/tenant_b labels are sorted-UUID order, not tied to
    which dev_seed slug (or which seeded user) they came from, so
    `seeded_actors[(tenant_a, "evaluation_owner")]` is NOT guaranteed to be
    owner.a's membership - it could just as easily be owner.b's. This avoids
    that assumption entirely for tests that need a specific known user."""
    users = UserRepository(mongo_test_db)
    memberships = MembershipRepository(mongo_test_db)
    user_doc = users.find_by_email(email)
    assert user_doc is not None, f"no seeded user for {email!r}"
    matches = [doc for doc in memberships.find_all_for_user(user_doc["_id"]) if doc["role"] == role]
    assert len(matches) == 1, f"expected exactly one {role!r} membership for {email!r}"
    return str(matches[0]["_id"])


def test_login_succeeds_and_issues_pre_session_token(client, seeded_actors) -> None:
    response = _login(client, "owner.a@dev.procurawise.local")

    assert response.status_code == 200
    body = response.json()
    assert body["pre_session_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0


def test_login_rejects_wrong_password(client, seeded_actors) -> None:
    response = _login(client, "owner.a@dev.procurawise.local", password="wrong-password")
    assert response.status_code == 401


def test_login_rejects_unknown_email(client, seeded_actors) -> None:
    response = _login(client, "does-not-exist@dev.procurawise.local")
    assert response.status_code == 401


def test_login_rejects_oidc_only_user_attempting_a_password(
    client, seeded_actors, mongo_test_db
) -> None:
    # A user with no password_hash at all (OIDC-only account) must not be
    # loginable via /auth/login with any password - same generic 401 as a
    # wrong password or unknown email, never distinguished.
    users = UserRepository(mongo_test_db)
    user = User.create(display_name="OIDC Only", email="oidc-only@dev.procurawise.local")
    users.insert(user.to_document())

    response = _login(client, "oidc-only@dev.procurawise.local", password="anything")
    assert response.status_code == 401


def test_memberships_requires_bearer_token(client) -> None:
    response = client.get("/api/v1/auth/memberships")
    assert response.status_code == 401


def test_memberships_lists_only_buyer_roles_for_authenticated_user(client, seeded_actors) -> None:
    # owner.b@dev.procurawise.local is seeded (dev_seed.py) with both an
    # evaluation_owner and an evaluator Membership under tenant_b - never
    # vendor_contact (that's a different seeded user entirely).
    token = _pre_session_token(client, "owner.b@dev.procurawise.local")

    response = client.get("/api/v1/auth/memberships", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    roles = {m["role"] for m in response.json()["memberships"]}
    assert roles == {"evaluation_owner", "evaluator"}


def test_switch_tenant_issues_access_token_for_owned_membership(
    client, seeded_actors, mongo_test_db
) -> None:
    membership_id = _membership_id_for(
        mongo_test_db, "owner.a@dev.procurawise.local", "evaluation_owner"
    )
    token = _pre_session_token(client, "owner.a@dev.procurawise.local")

    response = client.post(
        "/api/v1/auth/switch-tenant",
        json={"membership_id": membership_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["actor"]["membership_id"] == membership_id
    assert body["actor"]["role"] == "evaluation_owner"
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0

    # The minted access token actually authenticates against a real buyer
    # route (not just structurally correct in the response body).
    access_response = client.get(
        "/api/v1/vendor-organizations",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert access_response.status_code == 200


def test_switch_tenant_rejects_membership_belonging_to_other_user(
    client, seeded_actors, mongo_test_db
) -> None:
    other_users_membership_id = _membership_id_for(
        mongo_test_db, "owner.b@dev.procurawise.local", "evaluation_owner"
    )
    token = _pre_session_token(client, "owner.a@dev.procurawise.local")

    response = client.post(
        "/api/v1/auth/switch-tenant",
        json={"membership_id": other_users_membership_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_switch_tenant_rejects_unknown_membership_id(client, seeded_actors) -> None:
    token = _pre_session_token(client, "owner.a@dev.procurawise.local")

    response = client.post(
        "/api/v1/auth/switch-tenant",
        json={"membership_id": "does-not-exist"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_switch_tenant_rejects_own_vendor_contact_membership(
    client, seeded_actors, mongo_test_db
) -> None:
    """Even a Membership that DOES belong to the authenticated user is
    rejected if its role is vendor_contact - the buyer login flow can never
    mint an access token for the interim vendor mechanism (AUTH-PROD scope
    decision #1). Seeds an extra vendor_contact Membership under owner_a's
    own user_id (dev_seed.py has no such combination) to isolate the role
    check from the "not my membership" check already covered above."""
    owner_membership_id = _membership_id_for(
        mongo_test_db, "owner.a@dev.procurawise.local", "evaluation_owner"
    )

    memberships = MembershipRepository(mongo_test_db)
    owner_doc = memberships.find_by_id(owner_membership_id)
    owner_user_id = owner_doc["user_id"]
    owner_tenant_id = owner_doc["tenant_id"]

    vendor_orgs = VendorOrganizationRepository(mongo_test_db)
    vendor_org = VendorOrganization.create(tenant_id=owner_tenant_id, name="Owner-as-vendor probe")
    vendor_orgs.insert(owner_tenant_id, vendor_org.to_document())
    extra_membership = Membership.create(
        tenant_id=owner_tenant_id,
        user_id=owner_user_id,
        role="vendor_contact",
        vendor_org_id=vendor_org.id,
    )
    memberships.insert(extra_membership.to_document())

    token = _pre_session_token(client, "owner.a@dev.procurawise.local")
    response = client.post(
        "/api/v1/auth/switch-tenant",
        json={"membership_id": extra_membership.id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403

    # Also never offered through /auth/memberships in the first place.
    memberships_response = client.get(
        "/api/v1/auth/memberships", headers={"Authorization": f"Bearer {token}"}
    )
    membership_ids = {m["membership_id"] for m in memberships_response.json()["memberships"]}
    assert extra_membership.id not in membership_ids


def test_switch_tenant_requires_bearer_token(client) -> None:
    response = client.post("/api/v1/auth/switch-tenant", json={"membership_id": "anything"})
    assert response.status_code == 401


def test_pre_session_token_cannot_be_used_as_an_access_token(client, seeded_actors) -> None:
    """A pre-session token proves "this is a real user", not "this is a
    resolved tenant/role" - it must never work directly against a buyer
    route (only /auth/memberships and /auth/switch-tenant accept it)."""
    token = _pre_session_token(client, "owner.a@dev.procurawise.local")

    response = client.get(
        "/api/v1/vendor-organizations", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401


def test_vendor_contact_cannot_login_via_password(client, seeded_actors, mongo_test_db) -> None:
    """vendor_contact users are never given a password (dev_seed.py leaves
    vendor.a@dev.procurawise.local without one) - confirms /auth/login can't
    be used to bootstrap a vendor session even by accident."""
    _tenant_a, _vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    response = _login(client, "vendor.a@dev.procurawise.local", password="anything")
    assert response.status_code == 401


# --- OIDC (Microsoft/Google) ------------------------------------------------
# Every test below overrides get_oidc_provider with FakeOidcProvider - zero
# network calls, zero real OAuth app registrations (AUTH-PROD Bloque 3). The
# `client` fixture's teardown (tests/conftest.py) clears ALL
# app.dependency_overrides after each test, so no override here leaks into a
# later test even without the explicit _clear_oidc_override() calls below.


def _override_oidc(claims: OidcIdentityClaims) -> None:
    app.dependency_overrides[get_oidc_provider] = lambda: FakeOidcProvider(claims=claims)


def _clear_oidc_override() -> None:
    app.dependency_overrides.pop(get_oidc_provider, None)


def _state_from_login_redirect(client, provider: str = "microsoft") -> str:
    response = client.get(f"/api/v1/auth/oidc/{provider}/login", follow_redirects=False)
    assert response.status_code == 302
    query = parse_qs(urlsplit(response.headers["location"]).query)
    return query["state"][0]


def test_oidc_login_redirects_to_provider_authorization_url(client) -> None:
    _override_oidc(OidcIdentityClaims(email="x@example.com", subject="sub", email_verified=True))
    try:
        response = client.get("/api/v1/auth/oidc/microsoft/login", follow_redirects=False)
        assert response.status_code == 302
        location = response.headers["location"]
        assert location.startswith("https://idp.example.test/authorize")
        assert "state=" in location
        assert "nonce=" in location
    finally:
        _clear_oidc_override()


def test_oidc_login_returns_503_when_provider_not_configured(client) -> None:
    # No override here - exercises the REAL AuthlibOidcProvider factory
    # (get_oidc_provider) directly, whose OidcConfigurationError fires
    # because test Settings has no oidc_google_client_id/secret configured.
    response = client.get("/api/v1/auth/oidc/google/login", follow_redirects=False)
    assert response.status_code == 503


def test_oidc_callback_links_existing_user_by_verified_email(client, seeded_actors) -> None:
    claims = OidcIdentityClaims(
        email="owner.a@dev.procurawise.local", subject="ms-subject-1", email_verified=True
    )
    _override_oidc(claims)
    try:
        state = _state_from_login_redirect(client)
        response = client.get(
            "/api/v1/auth/oidc/microsoft/callback",
            params={"code": "fake-code", "state": state},
            follow_redirects=False,
        )
        assert response.status_code == 302
        location = response.headers["location"]
        assert location.startswith("http://localhost:5173/auth/callback#")
        fragment = parse_qs(urlsplit(location).fragment)
        pre_session_token = fragment["pre_session_token"][0]
        assert pre_session_token

        # The pre-session token actually works end to end: list memberships
        # with it, same as a password login would.
        memberships_response = client.get(
            "/api/v1/auth/memberships",
            headers={"Authorization": f"Bearer {pre_session_token}"},
        )
        assert memberships_response.status_code == 200
        assert memberships_response.json()["memberships"]
    finally:
        _clear_oidc_override()


def test_oidc_callback_rejects_unprovisioned_email(client, seeded_actors) -> None:
    claims = OidcIdentityClaims(
        email="nobody@dev.procurawise.local", subject="ms-subject-2", email_verified=True
    )
    _override_oidc(claims)
    try:
        state = _state_from_login_redirect(client)
        response = client.get(
            "/api/v1/auth/oidc/microsoft/callback",
            params={"code": "fake-code", "state": state},
            follow_redirects=False,
        )
        assert response.status_code == 403
    finally:
        _clear_oidc_override()


def test_oidc_callback_rejects_unverified_email_on_first_link(client, seeded_actors) -> None:
    claims = OidcIdentityClaims(
        email="owner.b@dev.procurawise.local", subject="ms-subject-3", email_verified=False
    )
    _override_oidc(claims)
    try:
        state = _state_from_login_redirect(client)
        response = client.get(
            "/api/v1/auth/oidc/microsoft/callback",
            params={"code": "fake-code", "state": state},
            follow_redirects=False,
        )
        assert response.status_code == 403
    finally:
        _clear_oidc_override()


def test_oidc_callback_rejects_invalid_state(client) -> None:
    _override_oidc(OidcIdentityClaims(email="x@example.com", subject="sub", email_verified=True))
    try:
        response = client.get(
            "/api/v1/auth/oidc/microsoft/callback",
            params={"code": "fake-code", "state": "not-a-real-state-token"},
            follow_redirects=False,
        )
        assert response.status_code == 400
    finally:
        _clear_oidc_override()


def test_oidc_callback_second_login_reuses_linked_identity(client, seeded_actors) -> None:
    """First callback links owner.a to microsoft/ms-subject-4 (email
    verified); a second callback with the SAME subject must succeed again
    even when the IdP now reports email_verified=False - already_linked
    short-circuits that check, which only guards the first, trust-
    establishing link, not every subsequent login."""
    first_claims = OidcIdentityClaims(
        email="owner.a@dev.procurawise.local", subject="ms-subject-4", email_verified=True
    )
    _override_oidc(first_claims)
    try:
        state_1 = _state_from_login_redirect(client)
        first = client.get(
            "/api/v1/auth/oidc/microsoft/callback",
            params={"code": "fake-code", "state": state_1},
            follow_redirects=False,
        )
        assert first.status_code == 302

        replay_claims = OidcIdentityClaims(
            email="owner.a@dev.procurawise.local", subject="ms-subject-4", email_verified=False
        )
        _override_oidc(replay_claims)
        state_2 = _state_from_login_redirect(client)
        second = client.get(
            "/api/v1/auth/oidc/microsoft/callback",
            params={"code": "fake-code", "state": state_2},
            follow_redirects=False,
        )
        assert second.status_code == 302
    finally:
        _clear_oidc_override()
