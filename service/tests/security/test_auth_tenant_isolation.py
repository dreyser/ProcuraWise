import time

import pytest

from procurawise.identity.jwt_provider import create_access_token
from procurawise.identity.repository import MembershipRepository, TenantRepository, UserRepository
from procurawise.identity.service import IdentityService
from procurawise.shared.mongo import get_database
from tests.conftest import bearer_headers_for, tenant_ids

pytestmark = pytest.mark.docker

# Mirrors tests/security/test_tenant_isolation.py's guarantees, but for the
# real JWT mechanism buyer routes use after AUTH-PROD - that file documents
# the interim dev-header mechanism (still used by vendor_contact), this one
# documents the production one. Cross-tenant data isolation itself (404 on
# another tenant's resource) is already exercised end-to-end with real
# bearer tokens in tests/security/test_vendor_isolation.py; this file focuses
# on what's new here specifically: token validity itself.


def test_missing_bearer_token_returns_401(client) -> None:
    assert client.get("/api/v1/vendor-organizations").status_code == 401


def test_malformed_authorization_header_returns_401(client) -> None:
    response = client.get(
        "/api/v1/vendor-organizations", headers={"Authorization": "not-a-bearer-token"}
    )
    assert response.status_code == 401


def test_tampered_access_token_returns_401(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _tenant_b = tenant_ids(seeded_actors)
    headers = bearer_headers_for(seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings)
    token = headers["Authorization"].removeprefix("Bearer ")
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

    response = client.get(
        "/api/v1/vendor-organizations", headers={"Authorization": f"Bearer {tampered}"}
    )
    assert response.status_code == 401


def test_expired_access_token_returns_401(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _tenant_b = tenant_ids(seeded_actors)
    membership_id = seeded_actors[(tenant_a, "evaluation_owner")]

    db = get_database(mongo_test_settings)
    identity_service = IdentityService(
        tenants=TenantRepository(db), users=UserRepository(db), memberships=MembershipRepository(db)
    )
    context = identity_service.resolve_actor_context(membership_id)
    expired_settings = mongo_test_settings.model_copy(update={"access_token_ttl_minutes": 0})
    token, _ = create_access_token(context, expired_settings)
    time.sleep(1)

    response = client.get(
        "/api/v1/vendor-organizations", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401
