import pytest

from procurawise.identity.dev_provider import DEV_ACTOR_HEADER
from procurawise.identity.models import VendorOrganization
from procurawise.identity.repository import VendorOrganizationRepository
from tests.conftest import bearer_headers_for, tenant_ids, unique_actor_by_role

pytestmark = pytest.mark.docker


def test_owner_lists_only_own_tenant_vendor_organizations(
    client, seeded_actors, mongo_test_db, mongo_test_settings
) -> None:
    # `tenant_ids()` labels are sorted-UUID order, not tied to which dev_seed
    # slug they came from (see its docstring) - never assume either label
    # carries the seeded "Proveedor Uno (dev)" baseline; insert known-named
    # organizations into both instead of relying on that baseline.
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )

    repo = VendorOrganizationRepository(mongo_test_db)
    own_tenant_vendor = VendorOrganization.create(
        tenant_id=tenant_a, name="Proveedor propio del tenant"
    )
    other_tenant_vendor = VendorOrganization.create(
        tenant_id=tenant_b, name="Proveedor de otro tenant"
    )
    repo.insert(tenant_a, own_tenant_vendor.to_document())
    repo.insert(tenant_b, other_tenant_vendor.to_document())

    response = client.get("/api/v1/vendor-organizations", headers=owner_a_headers)

    assert response.status_code == 200
    body = response.json()
    names = {item["name"] for item in body["items"]}
    assert "Proveedor propio del tenant" in names
    assert "Proveedor de otro tenant" not in names
    assert all("tenant_id" not in item for item in body["items"])


def test_evaluator_can_list_vendor_organizations(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _tenant_b = tenant_ids(seeded_actors)
    evaluator_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluator")], mongo_test_settings
    )

    response = client.get("/api/v1/vendor-organizations", headers=evaluator_headers)

    assert response.status_code == 200


def test_vendor_contact_cannot_list_vendor_organizations(client, seeded_actors) -> None:
    # vendor_contact never gets a real access token for buyer routes (AUTH-PROD
    # scope decision #1 - only the interim dev header, which the vendor
    # portal itself understands, not shared.context.require_role anymore).
    # Sending that dev header here now fails at authentication (401, missing
    # bearer token), before role-checking (403) ever runs - a strictly
    # stronger isolation guarantee than before.
    _tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    vendor_headers = {DEV_ACTOR_HEADER: vendor_membership_id}

    response = client.get("/api/v1/vendor-organizations", headers=vendor_headers)

    assert response.status_code == 401


def test_search_with_unbalanced_regex_syntax_is_treated_as_a_literal(
    client, seeded_actors, mongo_test_db, mongo_test_settings
) -> None:
    """`(` alone is invalid, unbalanced regex syntax - if the search term
    were interpolated into the Mongo `$regex` unescaped, this would fail
    with a server-side regex compile error instead of a normal 200."""
    tenant_a, _tenant_b = tenant_ids(seeded_actors)
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )

    repo = VendorOrganizationRepository(mongo_test_db)
    tricky = VendorOrganization.create(tenant_id=tenant_a, name="Proveedor (Beta)")
    repo.insert(tenant_a, tricky.to_document())

    response = client.get(
        "/api/v1/vendor-organizations",
        params={"search": "Proveedor ("},
        headers=owner_headers,
    )

    assert response.status_code == 200
    names = {item["name"] for item in response.json()["items"]}
    assert "Proveedor (Beta)" in names


def test_limit_above_maximum_is_rejected(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _tenant_b = tenant_ids(seeded_actors)
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )

    response = client.get(
        "/api/v1/vendor-organizations", params={"limit": 101}, headers=owner_headers
    )

    assert response.status_code == 422


def test_invalid_cursor_is_rejected(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _tenant_b = tenant_ids(seeded_actors)
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )

    response = client.get(
        "/api/v1/vendor-organizations",
        params={"cursor": "not-a-valid-cursor"},
        headers=owner_headers,
    )

    assert response.status_code == 422


def test_tenant_without_vendor_organizations_returns_empty_page(
    client, seeded_actors, mongo_test_db, mongo_test_settings
) -> None:
    # Resolve "the tenant with zero vendor organizations" from the database
    # itself - dev_seed always leaves exactly one of the two tenants without
    # one, but *which* label (tenant_a/tenant_b) that is varies per run.
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    empty_tenant = next(
        tenant_id
        for tenant_id in (tenant_a, tenant_b)
        if mongo_test_db["vendor_organizations"].count_documents({"tenant_id": tenant_id}) == 0
    )
    owner_headers = bearer_headers_for(
        seeded_actors[(empty_tenant, "evaluation_owner")], mongo_test_settings
    )

    response = client.get("/api/v1/vendor-organizations", headers=owner_headers)

    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}


def test_pagination_across_pages_is_stable_and_exhaustive(
    client, seeded_actors, mongo_test_db, mongo_test_settings
) -> None:
    tenant_a, _tenant_b = tenant_ids(seeded_actors)
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )

    initial_count = mongo_test_db["vendor_organizations"].count_documents({"tenant_id": tenant_a})
    inserted_names = ["Alfa Solutions", "Beta Software", "Gamma Systems", "Delta Tech"]
    repo = VendorOrganizationRepository(mongo_test_db)
    for name in inserted_names:
        repo.insert(
            tenant_a, VendorOrganization.create(tenant_id=tenant_a, name=name).to_document()
        )
    expected_total = initial_count + len(inserted_names)

    all_names: list[str] = []
    cursor: str | None = None
    pages_fetched = 0
    while True:
        params = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        page = client.get("/api/v1/vendor-organizations", params=params, headers=owner_headers)
        assert page.status_code == 200
        body = page.json()
        assert len(body["items"]) <= 2
        all_names.extend(item["name"] for item in body["items"])
        pages_fetched += 1
        assert pages_fetched <= expected_total, "pagination did not terminate as expected"
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert len(all_names) == expected_total
    assert set(inserted_names).issubset(all_names)
    assert all_names == sorted(all_names)
