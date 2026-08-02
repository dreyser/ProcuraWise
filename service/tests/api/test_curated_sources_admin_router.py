import pytest

from procurawise.dev_seed import DEV_ADMIN_EMAIL, DEV_ADMIN_PASSWORD
from tests.conftest import bearer_headers_for, tenant_ids, unique_actor_by_role

pytestmark = pytest.mark.docker


@pytest.fixture(autouse=True)
def _clean_curated_sources(mongo_test_db):
    yield
    mongo_test_db["curated_sources"].drop()


def _admin_headers(client) -> dict[str, str]:
    response = client.post(
        "/api/v1/admin/auth/login",
        json={"email": DEV_ADMIN_EMAIL, "password": DEV_ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_source(client, admin_headers, **overrides) -> dict:  # noqa: ANN003
    body = {
        "title": "Gartner ERP guide",
        "url": "https://example.com/erp-guide",
        "summary": "Guía curada de criterios para evaluar ERP en la nube",
        "tags": ["erp"],
    }
    body.update(overrides)
    response = client.post("/api/v1/admin/curated-sources", json=body, headers=admin_headers)
    assert response.status_code == 201
    return response.json()


# --- Founder-prioritized security tests: platform-admin vs buyer/tenant-admin boundary ---


def test_buyer_token_cannot_access_curated_sources_admin_routes(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _tenant_b = tenant_ids(seeded_actors)
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )

    assert client.get("/api/v1/admin/curated-sources", headers=owner_headers).status_code == 401
    assert (
        client.post(
            "/api/v1/admin/curated-sources",
            json={"title": "t", "url": "https://x", "summary": "s", "tags": []},
            headers=owner_headers,
        ).status_code
        == 401
    )


def test_tenant_admin_token_cannot_access_curated_sources_admin_routes(
    client, seeded_actors, mongo_test_settings
) -> None:
    _tenant_id, membership_id = unique_actor_by_role(seeded_actors, "tenant_admin")
    tenant_admin_headers = bearer_headers_for(membership_id, mongo_test_settings)

    response = client.get("/api/v1/admin/curated-sources", headers=tenant_admin_headers)
    assert response.status_code == 401


def test_admin_token_cannot_access_buyer_evaluation_routes(client, seeded_actors) -> None:
    admin_headers = _admin_headers(client)
    response = client.get("/api/v1/evaluations", headers=admin_headers)
    assert response.status_code == 401


def test_unauthenticated_request_is_rejected(client) -> None:
    response = client.get("/api/v1/admin/curated-sources")
    assert response.status_code == 401


# --- CRUD flow ---


def test_create_and_list_curated_source(client) -> None:
    admin_headers = _admin_headers(client)
    created = _create_source(client, admin_headers)
    assert created["active"] is True
    assert created["title"] == "Gartner ERP guide"

    listed = client.get("/api/v1/admin/curated-sources", headers=admin_headers)
    assert listed.status_code == 200
    ids = {item["id"] for item in listed.json()["items"]}
    assert created["id"] in ids


def test_update_curated_source_metadata(client) -> None:
    admin_headers = _admin_headers(client)
    created = _create_source(client, admin_headers)

    updated = client.patch(
        f"/api/v1/admin/curated-sources/{created['id']}",
        json={"summary": "Resumen actualizado"},
        headers=admin_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["summary"] == "Resumen actualizado"
    assert updated.json()["title"] == "Gartner ERP guide"  # unchanged


def test_deactivate_then_activate_is_soft_not_hard_delete(client) -> None:
    admin_headers = _admin_headers(client)
    created = _create_source(client, admin_headers)

    deactivated = client.post(
        f"/api/v1/admin/curated-sources/{created['id']}/deactivate", headers=admin_headers
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["active"] is False

    # Still resolvable by id after deactivation (soft delete, not hard
    # delete) - founder decision, Fase 14 planning: historical AIExecution
    # citations must remain attributable to a real admin record.
    listed = client.get("/api/v1/admin/curated-sources", headers=admin_headers)
    ids = {item["id"] for item in listed.json()["items"]}
    assert created["id"] in ids

    activated = client.post(
        f"/api/v1/admin/curated-sources/{created['id']}/activate", headers=admin_headers
    )
    assert activated.status_code == 200
    assert activated.json()["active"] is True


def test_update_unknown_source_is_404(client) -> None:
    admin_headers = _admin_headers(client)
    response = client.patch(
        "/api/v1/admin/curated-sources/does-not-exist",
        json={"title": "x"},
        headers=admin_headers,
    )
    assert response.status_code == 404


def test_deactivate_unknown_source_is_404(client) -> None:
    admin_headers = _admin_headers(client)
    response = client.post(
        "/api/v1/admin/curated-sources/does-not-exist/deactivate", headers=admin_headers
    )
    assert response.status_code == 404
