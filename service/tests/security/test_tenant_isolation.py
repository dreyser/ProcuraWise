import pytest
from fastapi.testclient import TestClient

from procurawise.api.main import app
from procurawise.dev_seed import seed
from procurawise.identity.dev_provider import DEV_ACTOR_HEADER
from procurawise.identity.models import VendorOrganization
from procurawise.identity.repository import VendorOrganizationRepository
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.tenant_collection import TenantCollection
from tests.conftest import tenant_ids as _tenant_ids
from tests.conftest import unique_actor_by_role as _unique_actor_by_role

pytestmark = pytest.mark.docker


def test_dev_actor_header_missing_returns_401(client) -> None:
    response = client.get("/api/v1/me")
    assert response.status_code == 401


def test_unknown_membership_id_returns_401(client) -> None:
    response = client.get("/api/v1/me", headers={DEV_ACTOR_HEADER: "does-not-exist"})
    assert response.status_code == 401


def test_owner_me_resolves_own_tenant_and_role(client, seeded_actors) -> None:
    tenant_a, _tenant_b = _tenant_ids(seeded_actors)
    owner_membership_id = seeded_actors[(tenant_a, "evaluation_owner")]

    response = client.get("/api/v1/me", headers={DEV_ACTOR_HEADER: owner_membership_id})

    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == tenant_a
    assert body["role"] == "evaluation_owner"


def test_vendor_contact_me_resolves_vendor_org_id(client, seeded_actors) -> None:
    vendor_tenant_id, vendor_membership_id = _unique_actor_by_role(seeded_actors, "vendor_contact")

    response = client.get("/api/v1/me", headers={DEV_ACTOR_HEADER: vendor_membership_id})

    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == vendor_tenant_id
    assert body["role"] == "vendor_contact"
    assert body["vendor_org_id"] is not None


def test_dev_actor_from_tenant_a_and_tenant_b_resolve_to_different_tenants(
    client, seeded_actors
) -> None:
    tenant_a, tenant_b = _tenant_ids(seeded_actors)
    owner_a_id = seeded_actors[(tenant_a, "evaluation_owner")]
    owner_b_id = seeded_actors[(tenant_b, "evaluation_owner")]

    response_a = client.get("/api/v1/me", headers={DEV_ACTOR_HEADER: owner_a_id})
    response_b = client.get("/api/v1/me", headers={DEV_ACTOR_HEADER: owner_b_id})

    assert response_a.json()["tenant_id"] == tenant_a
    assert response_b.json()["tenant_id"] == tenant_b
    assert response_a.json()["tenant_id"] != response_b.json()["tenant_id"]


def test_dev_identity_disabled_outside_development(
    mongo_test_settings: Settings, seeded_actors
) -> None:
    tenant_a, _tenant_b = _tenant_ids(seeded_actors)
    owner_a_id = seeded_actors[(tenant_a, "evaluation_owner")]
    production_settings = mongo_test_settings.model_copy(
        update={"environment": "production", "queue_backend": "service_bus"}
    )

    app.dependency_overrides[get_settings] = lambda: production_settings
    try:
        with TestClient(app) as prod_client:
            assert prod_client.get("/api/v1/dev/actors").status_code == 404
            response = prod_client.get("/api/v1/me", headers={DEV_ACTOR_HEADER: owner_a_id})
            assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_vendor_organization_is_not_visible_from_another_tenants_scope(mongo_test_db) -> None:
    collection = mongo_test_db["vendor_organizations"]
    repo = VendorOrganizationRepository(mongo_test_db)
    vendor = VendorOrganization.create(
        tenant_id="isolation-tenant-a", name="Vendor isolation probe"
    )
    repo.insert("isolation-tenant-a", vendor.to_document())

    scoped_to_other_tenant = TenantCollection(collection, "isolation-tenant-b")

    assert scoped_to_other_tenant.find_one({"_id": vendor.id}) is None
    collection.delete_one({"_id": vendor.id})


def test_vendor_organizations_endpoint_excludes_other_tenants(client, seeded_actors) -> None:
    tenant_a, tenant_b = _tenant_ids(seeded_actors)
    owner_a_headers = {DEV_ACTOR_HEADER: seeded_actors[(tenant_a, "evaluation_owner")]}
    owner_b_headers = {DEV_ACTOR_HEADER: seeded_actors[(tenant_b, "evaluation_owner")]}

    response_a = client.get("/api/v1/vendor-organizations", headers=owner_a_headers)
    response_b = client.get("/api/v1/vendor-organizations", headers=owner_b_headers)

    names_a = {item["name"] for item in response_a.json()["items"]}
    names_b = {item["name"] for item in response_b.json()["items"]}
    assert names_a.isdisjoint(names_b)


def test_seed_dev_is_idempotent(mongo_test_settings: Settings, mongo_test_db) -> None:
    first = seed(mongo_test_settings)
    second = seed(mongo_test_settings)

    assert {m.id for m in first} == {m.id for m in second}
    assert mongo_test_db["memberships"].count_documents({}) == len(first)
