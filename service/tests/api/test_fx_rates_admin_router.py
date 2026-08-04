import pytest

from procurawise.dev_seed import DEV_ADMIN_EMAIL, DEV_ADMIN_PASSWORD
from tests.conftest import bearer_headers_for, tenant_ids, unique_actor_by_role

pytestmark = pytest.mark.docker


@pytest.fixture(autouse=True)
def _clean_fx_rates(mongo_test_db):
    yield
    mongo_test_db["fx_rates"].drop()


def _admin_headers(client) -> dict[str, str]:
    response = client.post(
        "/api/v1/admin/auth/login",
        json={"email": DEV_ADMIN_EMAIL, "password": DEV_ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_fx_rate(client, admin_headers, **overrides) -> dict:  # noqa: ANN003
    body = {
        "from_currency": "USD",
        "to_currency": "MXN",
        "rate": "18.50",
        "effective_date": "2026-08-01",
    }
    body.update(overrides)
    response = client.post("/api/v1/admin/fx-rates", json=body, headers=admin_headers)
    assert response.status_code == 201
    return response.json()


# --- Founder-prioritized security tests: platform-admin vs buyer/tenant-admin boundary ---


def test_buyer_token_cannot_access_fx_rates_admin_routes(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _tenant_b = tenant_ids(seeded_actors)
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )

    assert client.get("/api/v1/admin/fx-rates", headers=owner_headers).status_code == 401
    assert (
        client.post(
            "/api/v1/admin/fx-rates",
            json={
                "from_currency": "USD",
                "to_currency": "MXN",
                "rate": "18.5",
                "effective_date": "2026-08-01",
            },
            headers=owner_headers,
        ).status_code
        == 401
    )


def test_tenant_admin_token_cannot_access_fx_rates_admin_routes(
    client, seeded_actors, mongo_test_settings
) -> None:
    _tenant_id, membership_id = unique_actor_by_role(seeded_actors, "tenant_admin")
    tenant_admin_headers = bearer_headers_for(membership_id, mongo_test_settings)

    response = client.get("/api/v1/admin/fx-rates", headers=tenant_admin_headers)
    assert response.status_code == 401


def test_unauthenticated_request_is_rejected(client) -> None:
    response = client.get("/api/v1/admin/fx-rates")
    assert response.status_code == 401


# --- CRUD flow (create-only, plan §9 R4) ---


def test_create_and_list_fx_rate(client) -> None:
    admin_headers = _admin_headers(client)
    created = _create_fx_rate(client, admin_headers)
    assert created["from_currency"] == "USD"
    assert created["to_currency"] == "MXN"
    assert created["rate"] == "18.50"
    assert created["source"] == "manual"

    listed = client.get("/api/v1/admin/fx-rates", headers=admin_headers)
    assert listed.status_code == 200
    ids = {item["id"] for item in listed.json()["items"]}
    assert created["id"] in ids


def test_create_fx_rate_rejects_currency_outside_mxn_usd(client) -> None:
    admin_headers = _admin_headers(client)
    response = client.post(
        "/api/v1/admin/fx-rates",
        json={
            "from_currency": "EUR",
            "to_currency": "MXN",
            "rate": "20",
            "effective_date": "2026-08-01",
        },
        headers=admin_headers,
    )
    assert response.status_code == 422


def test_multiple_rates_for_same_pair_are_all_listed_newest_first_by_effective_date(
    client,
) -> None:
    admin_headers = _admin_headers(client)
    _create_fx_rate(client, admin_headers, rate="18.00", effective_date="2026-07-01")
    _create_fx_rate(client, admin_headers, rate="18.50", effective_date="2026-08-01")

    listed = client.get("/api/v1/admin/fx-rates", headers=admin_headers)
    rates = [item["rate"] for item in listed.json()["items"]]
    assert rates[0] == "18.50"
    assert rates[1] == "18.00"
