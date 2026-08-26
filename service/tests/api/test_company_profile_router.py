"""UAT-03 (R4): tenant_admin-only company profile settings (one row per
tenant, id == tenant_id, same 1:1 grain as billing.BillingAccount). Covers
role enforcement, the lazy-empty-on-first-read default, the full-replace
update, client field-tampering rejection, and tenant isolation."""

import pytest

from procurawise.identity.models import Membership, User
from procurawise.identity.repository import MembershipRepository, UserRepository
from tests.conftest import bearer_headers_for, tenant_ids, unique_actor_by_role

pytestmark = pytest.mark.docker


def _tenant_admin_headers_for(tenant_id: str, mongo_test_db, mongo_test_settings) -> dict[str, str]:
    """dev_seed.py only seeds one tenant_admin (tenant_a) - a second
    tenant's tenant_admin is created ad hoc here, same pattern as
    tests/api/test_review_approval.py's `other_membership`."""
    users = UserRepository(mongo_test_db)
    memberships = MembershipRepository(mongo_test_db)
    user = User.create(display_name="Other Tenant Admin", email="other.tenant.admin@dev.local")
    users.insert(user.to_document())
    membership = Membership.create(tenant_id=tenant_id, user_id=user.id, role="tenant_admin")
    memberships.insert(membership.to_document())
    return bearer_headers_for(membership.id, mongo_test_settings)


def _profile_body(**overrides: str) -> dict[str, str]:
    body = {
        "legal_name": "Acme Compras SA de CV",
        "tax_id": "ACO010101AAA",
        "address": "Av. Reforma 100, CDMX",
        "industry": "Manufactura",
        "website_url": "https://acme.example.com",
    }
    body.update(overrides)
    return body


def test_unauthenticated_request_is_rejected(client) -> None:
    response = client.get("/api/v1/company-profile")
    assert response.status_code == 401


def test_evaluation_owner_cannot_read_company_profile(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _tenant_admin = unique_actor_by_role(seeded_actors, "tenant_admin")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    response = client.get("/api/v1/company-profile", headers=owner_headers)
    assert response.status_code == 403


def test_evaluation_owner_cannot_update_company_profile(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _tenant_admin = unique_actor_by_role(seeded_actors, "tenant_admin")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    response = client.put("/api/v1/company-profile", json=_profile_body(), headers=owner_headers)
    assert response.status_code == 403


def test_get_returns_empty_profile_before_any_update(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_admin_membership_id = unique_actor_by_role(seeded_actors, "tenant_admin")
    tenant_admin_headers = bearer_headers_for(tenant_admin_membership_id, mongo_test_settings)

    response = client.get("/api/v1/company-profile", headers=tenant_admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["legal_name"] == ""
    assert body["tax_id"] == ""
    assert body["address"] == ""
    assert body["industry"] == ""
    assert body["website_url"] == ""


def test_update_rejects_a_non_http_website_url(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, tenant_admin_membership_id = unique_actor_by_role(seeded_actors, "tenant_admin")
    tenant_admin_headers = bearer_headers_for(tenant_admin_membership_id, mongo_test_settings)

    response = client.put(
        "/api/v1/company-profile",
        json=_profile_body(website_url="ftp://acme.example.com"),
        headers=tenant_admin_headers,
    )
    assert response.status_code == 422


def test_update_rejects_client_supplied_unknown_field(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_admin_membership_id = unique_actor_by_role(seeded_actors, "tenant_admin")
    tenant_admin_headers = bearer_headers_for(tenant_admin_membership_id, mongo_test_settings)

    response = client.put(
        "/api/v1/company-profile",
        json={**_profile_body(), "tenant_id": "some-other-tenant"},
        headers=tenant_admin_headers,
    )
    assert response.status_code == 422


def test_update_persists_and_is_audited(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    tenant_a, tenant_admin_membership_id = unique_actor_by_role(seeded_actors, "tenant_admin")
    tenant_admin_headers = bearer_headers_for(tenant_admin_membership_id, mongo_test_settings)

    update_response = client.put(
        "/api/v1/company-profile", json=_profile_body(), headers=tenant_admin_headers
    )
    assert update_response.status_code == 200, update_response.text
    body = update_response.json()
    assert body["legal_name"] == "Acme Compras SA de CV"
    assert body["website_url"] == "https://acme.example.com"

    get_response = client.get("/api/v1/company-profile", headers=tenant_admin_headers)
    assert get_response.json() == body

    # No evaluation-scoped audit-events route applies here (this action has
    # no evaluation_id) - read the append-only collection directly, same
    # pattern as tests/security/test_audit_isolation.py.
    audit_doc = mongo_test_db["audit_events"].find_one(
        {"tenant_id": tenant_a, "action": "company_profile_updated"}
    )
    assert audit_doc is not None
    assert audit_doc["resource_type"] == "company_profile"
    assert audit_doc["resource_id"] == tenant_a


def test_second_update_fully_replaces_the_previous_values(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_admin_membership_id = unique_actor_by_role(seeded_actors, "tenant_admin")
    tenant_admin_headers = bearer_headers_for(tenant_admin_membership_id, mongo_test_settings)

    client.put("/api/v1/company-profile", json=_profile_body(), headers=tenant_admin_headers)
    second = client.put(
        "/api/v1/company-profile",
        json=_profile_body(industry="Servicios", website_url=""),
        headers=tenant_admin_headers,
    )
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["industry"] == "Servicios"
    assert body["website_url"] == ""
    # Untouched fields are still whatever this same request sent - a
    # full-replace PUT, never a partial patch.
    assert body["legal_name"] == "Acme Compras SA de CV"


def test_company_profile_for_another_tenant_never_leaks(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    tenant_a, tenant_admin_a = unique_actor_by_role(seeded_actors, "tenant_admin")
    tenant_admin_a_headers = bearer_headers_for(tenant_admin_a, mongo_test_settings)
    client.put(
        "/api/v1/company-profile",
        json=_profile_body(legal_name="Tenant A Legal Name"),
        headers=tenant_admin_a_headers,
    )

    tenant_b = next(t for t in tenant_ids(seeded_actors) if t != tenant_a)
    tenant_admin_b_headers = _tenant_admin_headers_for(tenant_b, mongo_test_db, mongo_test_settings)
    response = client.get("/api/v1/company-profile", headers=tenant_admin_b_headers)
    assert response.status_code == 200
    assert response.json()["legal_name"] != "Tenant A Legal Name"
    assert response.json()["legal_name"] == ""
