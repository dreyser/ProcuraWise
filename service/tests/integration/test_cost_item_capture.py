import pytest

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


def _minimal_cost_item(**overrides) -> dict:  # noqa: ANN003
    body = {
        "concept": "Licencias",
        "category": "recurring",
        "billing_unit": "usuario",
        "quantity": "10",
        "unit_price": "199.99",
        "currency": "MXN",
        "frequency_per_year": "1",
        "year_start": 1,
        "year_end": 1,
        "cost_type": "recurring",
        "expected_version": 1,
    }
    body.update(overrides)
    return body


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
        json={"name": "TCO capture RFP", "description": ""},
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
    return evaluation_id, proposal_id, vendor_headers, vendor_org_id


def test_add_cost_item_appears_in_proposal_and_bumps_version(
    client, seeded_actors, mongo_test_settings
) -> None:
    _evaluation_id, proposal_id, vendor_headers, _vendor_org_id = _setup_draft_proposal(
        client, seeded_actors, mongo_test_settings
    )
    response = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/cost-items",
        json=_minimal_cost_item(),
        headers=vendor_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 2
    assert len(body["cost_items"]) == 1
    assert body["cost_items"][0]["concept"] == "Licencias"
    assert body["cost_items"][0]["unit_price"] == "199.99"


def test_add_cost_item_with_stale_version_is_409(
    client, seeded_actors, mongo_test_settings
) -> None:
    _evaluation_id, proposal_id, vendor_headers, _vendor_org_id = _setup_draft_proposal(
        client, seeded_actors, mongo_test_settings
    )
    response = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/cost-items",
        json=_minimal_cost_item(expected_version=999),
        headers=vendor_headers,
    )
    assert response.status_code == 409


def test_add_cost_item_with_year_start_after_year_end_is_422(
    client, seeded_actors, mongo_test_settings
) -> None:
    _evaluation_id, proposal_id, vendor_headers, _vendor_org_id = _setup_draft_proposal(
        client, seeded_actors, mongo_test_settings
    )
    response = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/cost-items",
        json=_minimal_cost_item(year_start=3, year_end=1),
        headers=vendor_headers,
    )
    assert response.status_code == 422


def test_update_cost_item_changes_only_provided_fields(
    client, seeded_actors, mongo_test_settings
) -> None:
    _evaluation_id, proposal_id, vendor_headers, _vendor_org_id = _setup_draft_proposal(
        client, seeded_actors, mongo_test_settings
    )
    created = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/cost-items",
        json=_minimal_cost_item(),
        headers=vendor_headers,
    ).json()
    cost_item_id = created["cost_items"][0]["id"]

    updated = client.put(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/cost-items/{cost_item_id}",
        json={"unit_price": "250.00", "expected_version": created["version"]},
        headers=vendor_headers,
    )
    assert updated.status_code == 200
    item = updated.json()["cost_items"][0]
    assert item["unit_price"] == "250.00"
    assert item["concept"] == "Licencias"  # unchanged


def test_update_unknown_cost_item_is_404(client, seeded_actors, mongo_test_settings) -> None:
    _evaluation_id, proposal_id, vendor_headers, _vendor_org_id = _setup_draft_proposal(
        client, seeded_actors, mongo_test_settings
    )
    response = client.put(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/cost-items/does-not-exist",
        json={"unit_price": "1", "expected_version": 1},
        headers=vendor_headers,
    )
    assert response.status_code == 404


def test_remove_cost_item(client, seeded_actors, mongo_test_settings) -> None:
    _evaluation_id, proposal_id, vendor_headers, _vendor_org_id = _setup_draft_proposal(
        client, seeded_actors, mongo_test_settings
    )
    created = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/cost-items",
        json=_minimal_cost_item(),
        headers=vendor_headers,
    ).json()
    cost_item_id = created["cost_items"][0]["id"]

    removed = client.delete(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/cost-items/{cost_item_id}"
        f"?expected_version={created['version']}",
        headers=vendor_headers,
    )
    assert removed.status_code == 200
    assert removed.json()["cost_items"] == []


def test_preview_tco_with_no_cost_items_is_zero(client, seeded_actors, mongo_test_settings) -> None:
    _evaluation_id, proposal_id, vendor_headers, _vendor_org_id = _setup_draft_proposal(
        client, seeded_actors, mongo_test_settings
    )
    response = client.get(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/tco-preview", headers=vendor_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["grand_total"] == "0.00"
    assert body["by_year"] == {}


def test_preview_tco_same_currency_as_base_needs_no_fx_rate(
    client, seeded_actors, mongo_test_settings
) -> None:
    _evaluation_id, proposal_id, vendor_headers, _vendor_org_id = _setup_draft_proposal(
        client, seeded_actors, mongo_test_settings
    )
    client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/cost-items",
        json=_minimal_cost_item(quantity="1", unit_price="1000", currency="MXN"),
        headers=vendor_headers,
    )
    response = client.get(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/tco-preview", headers=vendor_headers
    )
    assert response.status_code == 200
    assert response.json()["grand_total"] == "1000.00"


def test_preview_tco_missing_fx_rate_for_foreign_currency_is_422(
    client, seeded_actors, mongo_test_settings
) -> None:
    _evaluation_id, proposal_id, vendor_headers, _vendor_org_id = _setup_draft_proposal(
        client, seeded_actors, mongo_test_settings
    )
    client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/cost-items",
        json=_minimal_cost_item(quantity="1", unit_price="100", currency="USD"),
        headers=vendor_headers,
    )
    response = client.get(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/tco-preview", headers=vendor_headers
    )
    assert response.status_code == 422
