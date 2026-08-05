"""Fase 19 acceptance criterion (backlog.md fila 19): "TCO recalculado no
cambia al actualizar FXRate despues de publicacion." This file proves it
directly against the real submit()/FXRate-admin/buyer-read endpoints."""

import pytest

from procurawise.dev_seed import DEV_ADMIN_EMAIL, DEV_ADMIN_PASSWORD
from procurawise.identity.dev_provider import DEV_ACTOR_HEADER
from tests.conftest import (
    approve_and_publish,
    bearer_headers_for,
    unique_actor_by_role,
    vendor_bearer_headers_for,
)

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
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_fx_rate(client, admin_headers, **overrides) -> dict:  # noqa: ANN003
    body = {
        "from_currency": "USD",
        "to_currency": "MXN",
        "rate": "18.50",
        "effective_date": "2026-01-01",
    }
    body.update(overrides)
    response = client.post("/api/v1/admin/fx-rates", json=body, headers=admin_headers)
    assert response.status_code == 201
    return response.json()


def _setup_draft_proposal(client, seeded_actors, mongo_test_settings):
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    vendor_dev_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_dev_headers).json()["vendor_org_id"]
    vendor_headers = vendor_bearer_headers_for(vendor_membership_id, mongo_test_settings)

    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "TCO freeze RFP", "description": ""},
        headers=owner_headers,
    ).json()["id"]
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "functional",
            "category": "Core",
            "title": "Req 1",
            "description": "d",
            "priority": "important",
            "response_type": "text",
            "weight": 40.0,
            "required": False,
            "display_order": 1,
        },
        headers=owner_headers,
    )
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "technical",
            "category": "Core",
            "title": "Req 2",
            "description": "d",
            "priority": "important",
            "response_type": "text",
            "weight": 20.0,
            "required": False,
            "display_order": 2,
        },
        headers=owner_headers,
    )
    proposal_id = client.post(
        f"/api/v1/evaluations/{evaluation_id}/vendors",
        json={"vendor_org_id": vendor_org_id},
        headers=owner_headers,
    ).json()["id"]
    approver_membership_id = seeded_actors[(tenant_a, "approver")]
    approver_headers = bearer_headers_for(approver_membership_id, mongo_test_settings)
    approve_and_publish(
        client, owner_headers, approver_membership_id, approver_headers, evaluation_id
    )
    return evaluation_id, proposal_id, owner_headers, vendor_headers


def test_tco_frozen_at_submit_does_not_change_when_fx_rate_is_updated_afterward(
    client, seeded_actors, mongo_test_settings
) -> None:
    evaluation_id, proposal_id, owner_headers, vendor_headers = _setup_draft_proposal(
        client, seeded_actors, mongo_test_settings
    )
    admin_headers = _admin_headers(client)
    _create_fx_rate(client, admin_headers, rate="18.50", effective_date="2026-01-01")

    client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/cost-items",
        json={
            "concept": "Licencia anual",
            "category": "recurring",
            "billing_unit": "usuario",
            "quantity": "10",
            "unit_price": "100",
            "currency": "USD",
            "frequency_per_year": "1",
            "year_start": 1,
            "year_end": 1,
            "cost_type": "recurring",
            "expected_version": 1,
        },
        headers=vendor_headers,
    )
    submitted = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/submit",
        json={"expected_version": 2},
        headers=vendor_headers,
    )
    assert submitted.status_code == 200

    before = client.get(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/tco", headers=owner_headers
    )
    assert before.status_code == 200
    before_body = before.json()
    assert before_body["grand_total"] == "18500.00"  # 10 * 100 USD * 18.50
    assert before_body["fx_rates_used"][0]["rate"] == "18.50"

    # platform_admin publishes a materially different rate, dated after the
    # one already frozen into this snapshot.
    _create_fx_rate(client, admin_headers, rate="25.00", effective_date="2026-06-01")

    after = client.get(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/tco", headers=owner_headers
    )
    assert after.status_code == 200
    after_body = after.json()
    assert after_body["grand_total"] == before_body["grand_total"] == "18500.00"
    assert after_body["fx_rates_used"][0]["rate"] == "18.50"
    assert after_body["calculated_at"] == before_body["calculated_at"]


def test_submit_without_available_fx_rate_fails_closed_and_freezes_nothing(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    _evaluation_id, proposal_id, _owner_headers, vendor_headers = _setup_draft_proposal(
        client, seeded_actors, mongo_test_settings
    )
    client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/cost-items",
        json={
            "concept": "Licencia anual",
            "category": "recurring",
            "billing_unit": "usuario",
            "quantity": "1",
            "unit_price": "100",
            "currency": "USD",
            "frequency_per_year": "1",
            "year_start": 1,
            "year_end": 1,
            "cost_type": "recurring",
            "expected_version": 1,
        },
        headers=vendor_headers,
    )
    submitted = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/submit",
        json={"expected_version": 2},
        headers=vendor_headers,
    )
    assert submitted.status_code == 422

    doc = mongo_test_db["proposals"].find_one({"_id": proposal_id})
    assert doc["status"] == "draft"
    assert doc["snapshots"] == []
    assert doc["version"] == 2  # only the cost-item add bumped it, not the failed submit


def test_buyer_cannot_read_tco_before_proposal_is_submitted(
    client, seeded_actors, mongo_test_settings
) -> None:
    evaluation_id, proposal_id, owner_headers, _vendor_headers = _setup_draft_proposal(
        client, seeded_actors, mongo_test_settings
    )
    response = client.get(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/tco", headers=owner_headers
    )
    assert response.status_code == 404
