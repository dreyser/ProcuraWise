import pytest

from procurawise.identity.dev_provider import DEV_ACTOR_HEADER
from tests.conftest import unique_actor_by_role

pytestmark = pytest.mark.docker


def test_vertical_slice_happy_path(client, seeded_actors) -> None:
    """owner creates evaluation -> requirements -> links vendor -> starts
    collection -> vendor answers+submits -> owner starts evaluation ->
    scores -> results -> completes. Exercises the full VS-2B contract end to
    end against a real Mongo instance."""
    # dev_seed only seeds a vendor_contact under one tenant - resolve that
    # tenant by role rather than an arbitrary/sorted tenant pair.
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = {DEV_ACTOR_HEADER: seeded_actors[(tenant_a, "evaluation_owner")]}
    evaluator_headers = {DEV_ACTOR_HEADER: seeded_actors[(tenant_a, "evaluator")]}
    vendor_headers = {DEV_ACTOR_HEADER: vendor_membership_id}

    vendor_org_id = client.get("/api/v1/me", headers=vendor_headers).json()["vendor_org_id"]

    created = client.post(
        "/api/v1/evaluations",
        json={"name": "RFP CRM", "description": "Reemplazo de CRM"},
        headers=owner_headers,
    )
    assert created.status_code == 201
    evaluation_id = created.json()["id"]

    functional = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "functional",
            "category": "Core",
            "title": "Gestion de pedidos",
            "description": "Debe permitir gestionar pedidos end to end",
            "priority": "mandatory",
            "response_type": "compliant_status",
            "weight": 40.0,
            "required": True,
            "display_order": 1,
        },
        headers=owner_headers,
    )
    assert functional.status_code == 201
    functional_id = functional.json()["id"]

    technical = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "technical",
            "category": "Integraciones",
            "title": "Limite de llamadas API",
            "description": "Cuantas llamadas por minuto soporta la API",
            "priority": "important",
            "response_type": "number",
            "weight": 20.0,
            "required": True,
            "display_order": 1,
        },
        headers=owner_headers,
    )
    assert technical.status_code == 201
    technical_id = technical.json()["id"]

    link = client.post(
        f"/api/v1/evaluations/{evaluation_id}/vendors",
        json={"vendor_org_id": vendor_org_id},
        headers=owner_headers,
    )
    assert link.status_code == 201
    proposal_id = link.json()["id"]

    start_collection = client.post(
        f"/api/v1/evaluations/{evaluation_id}/start-collection", headers=owner_headers
    )
    assert start_collection.status_code == 200
    assert start_collection.json()["status"] == "collecting_responses"

    answer_functional = client.put(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/answers/{functional_id}",
        json={"value": "compliant", "expected_version": 1},
        headers=vendor_headers,
    )
    assert answer_functional.status_code == 200
    version = answer_functional.json()["version"]

    answer_technical = client.put(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/answers/{technical_id}",
        json={"value": 120, "expected_version": version},
        headers=vendor_headers,
    )
    assert answer_technical.status_code == 200
    version = answer_technical.json()["version"]

    submit = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/submit",
        json={"expected_version": version},
        headers=vendor_headers,
    )
    assert submit.status_code == 200
    assert submit.json()["status"] == "submitted"

    start_evaluation = client.post(
        f"/api/v1/evaluations/{evaluation_id}/start-evaluation", headers=owner_headers
    )
    assert start_evaluation.status_code == 200
    assert start_evaluation.json()["status"] == "evaluating"

    results_before_scoring = client.get(
        f"/api/v1/evaluations/{evaluation_id}/results", headers=owner_headers
    )
    assert results_before_scoring.status_code == 200
    assert results_before_scoring.json()["scoring_status"] == "incomplete"

    score_functional = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/scores/{functional_id}",
        json={"score": 5},
        headers=evaluator_headers,
    )
    assert score_functional.status_code == 200
    assert score_functional.json()["weighted_points"] == 40.0

    score_technical = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/scores/{technical_id}",
        json={"score": 4},
        headers=owner_headers,
    )
    assert score_technical.status_code == 200
    assert score_technical.json()["weighted_points"] == 16.0

    results = client.get(f"/api/v1/evaluations/{evaluation_id}/results", headers=owner_headers)
    assert results.status_code == 200
    body = results.json()
    assert body["result_status"] == "partial"
    assert body["is_final"] is False
    assert body["scoring_status"] == "complete"
    [proposal_result] = body["proposals"]
    assert proposal_result["functional"] == {"earned_points": 40.0, "maximum_points": 40.0}
    assert proposal_result["technical"] == {"earned_points": 16.0, "maximum_points": 20.0}
    assert proposal_result["economic"]["status"] == "not_available"
    assert proposal_result["economic"]["earned_points"] is None
    assert proposal_result["partial_result"]["earned_points"] == 56.0
    assert proposal_result["mandatory_alerts_count"] == 0
    assert body["draft_proposals"] == []

    # /results is the only read surface for an existing Score's version - the
    # scoring UI needs it to build a valid update (see scoring/schemas.py).
    scores_by_requirement = {s["requirement_id"]: s for s in proposal_result["scores"]}
    assert scores_by_requirement[functional_id]["version"] == 1
    assert scores_by_requirement[functional_id]["comment"] is None
    assert scores_by_requirement[technical_id]["version"] == 1

    rescored_functional = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/scores/{functional_id}",
        json={"score": 4, "comment": "Revisado", "version": 1},
        headers=evaluator_headers,
    )
    assert rescored_functional.status_code == 200
    assert rescored_functional.json()["version"] == 2
    assert rescored_functional.json()["comment"] == "Revisado"

    complete = client.post(f"/api/v1/evaluations/{evaluation_id}/complete", headers=owner_headers)
    assert complete.status_code == 200
    assert complete.json()["status"] == "completed"
