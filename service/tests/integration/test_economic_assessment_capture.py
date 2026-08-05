import pytest

from procurawise.identity.dev_provider import DEV_ACTOR_HEADER
from tests.conftest import (
    approve_and_publish,
    bearer_headers_for,
    unique_actor_by_role,
    vendor_bearer_headers_for,
)

pytestmark = pytest.mark.docker

_COMMERCIAL_KEYS = [
    "payment_terms",
    "price_protection",
    "contractual_flexibility",
    "discounts_incentives",
    "billing_transparency",
]
_RISK_KEYS = [
    "variable_cost_exposure",
    "increases_indexation",
    "assumptions_exclusions",
    "fx_fiscal_regulatory",
    "exit_portability_lockin",
]


def _full_scores(score_value: int, comment: str | None = None) -> list[dict]:
    return [
        {"criterion_key": key, "score": score_value, "comment": comment} for key in _COMMERCIAL_KEYS
    ]


def _risk_scores(score_value: int, comment: str | None = None) -> list[dict]:
    return [{"criterion_key": key, "score": score_value, "comment": comment} for key in _RISK_KEYS]


def _create_scoreable_proposal(
    client,
    owner_headers: dict,
    vendor_membership_id: str,
    *,
    tenant_id: str,
    seeded_actors: dict,
    mongo_test_settings,
) -> tuple[str, str]:
    """Same shape as test_section_scoped_scoring.py's helper, minus the
    requirement_id return (economic assessment isn't per-requirement)."""
    vendor_dev_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_dev_headers).json()["vendor_org_id"]
    vendor_headers = vendor_bearer_headers_for(vendor_membership_id, mongo_test_settings)

    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Assessment economico", "description": ""},
        headers=owner_headers,
    ).json()["id"]
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "functional",
            "category": "Core",
            "title": "T",
            "description": "D",
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
            "title": "T2",
            "description": "D2",
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
    approver_membership_id = seeded_actors[(tenant_id, "approver")]
    approver_headers = bearer_headers_for(approver_membership_id, mongo_test_settings)
    approve_and_publish(
        client, owner_headers, approver_membership_id, approver_headers, evaluation_id
    )
    client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/submit",
        json={"expected_version": 1},
        headers=vendor_headers,
    )
    client.post(f"/api/v1/evaluations/{evaluation_id}/start-evaluation", headers=owner_headers)
    return evaluation_id, proposal_id


def test_get_economic_assessment_is_404_before_first_write(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id, proposal_id = _create_scoreable_proposal(
        client,
        owner_headers,
        vendor_membership_id,
        tenant_id=tenant_a,
        seeded_actors=seeded_actors,
        mongo_test_settings=mongo_test_settings,
    )
    response = client.get(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/economic-assessment",
        headers=owner_headers,
    )
    assert response.status_code == 404


def test_get_economic_assessment_reflects_the_last_write(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id, proposal_id = _create_scoreable_proposal(
        client,
        owner_headers,
        vendor_membership_id,
        tenant_id=tenant_a,
        seeded_actors=seeded_actors,
        mongo_test_settings=mongo_test_settings,
    )
    client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/economic-assessment",
        json={"commercial_scores": _full_scores(4), "risk_scores": _risk_scores(3)},
        headers=owner_headers,
    )
    response = client.get(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/economic-assessment",
        headers=owner_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 1
    assert body["commercial_scores"][0]["score"] == 4


def test_owner_creates_and_updates_economic_assessment(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id, proposal_id = _create_scoreable_proposal(
        client,
        owner_headers,
        vendor_membership_id,
        tenant_id=tenant_a,
        seeded_actors=seeded_actors,
        mongo_test_settings=mongo_test_settings,
    )

    created = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/economic-assessment",
        json={"commercial_scores": _full_scores(4), "risk_scores": _risk_scores(3)},
        headers=owner_headers,
    )
    assert created.status_code == 200
    body = created.json()
    assert body["version"] == 1
    assert len(body["commercial_scores"]) == 5
    assert len(body["risk_scores"]) == 5

    updated = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/economic-assessment",
        json={
            "commercial_scores": _full_scores(5, comment="Excelente"),
            "risk_scores": _risk_scores(3),
            "version": 1,
        },
        headers=owner_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert updated.json()["commercial_scores"][0]["score"] == 5


def test_stale_version_is_409(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id, proposal_id = _create_scoreable_proposal(
        client,
        owner_headers,
        vendor_membership_id,
        tenant_id=tenant_a,
        seeded_actors=seeded_actors,
        mongo_test_settings=mongo_test_settings,
    )
    client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/economic-assessment",
        json={"commercial_scores": _full_scores(4), "risk_scores": _risk_scores(3)},
        headers=owner_headers,
    )
    response = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/economic-assessment",
        json={"commercial_scores": _full_scores(3), "risk_scores": _risk_scores(3), "version": 999},
        headers=owner_headers,
    )
    assert response.status_code == 409


def test_extreme_score_without_comment_is_422(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id, proposal_id = _create_scoreable_proposal(
        client,
        owner_headers,
        vendor_membership_id,
        tenant_id=tenant_a,
        seeded_actors=seeded_actors,
        mongo_test_settings=mongo_test_settings,
    )
    response = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/economic-assessment",
        # score=0 (extreme) with no comment on the first commercial criterion.
        json={"commercial_scores": _full_scores(0), "risk_scores": _risk_scores(3)},
        headers=owner_headers,
    )
    assert response.status_code == 422


def test_na_score_without_comment_is_422(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id, proposal_id = _create_scoreable_proposal(
        client,
        owner_headers,
        vendor_membership_id,
        tenant_id=tenant_a,
        seeded_actors=seeded_actors,
        mongo_test_settings=mongo_test_settings,
    )
    scores = _full_scores(3)
    scores[0] = {"criterion_key": "payment_terms", "score": None, "comment": None}
    response = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/economic-assessment",
        json={"commercial_scores": scores, "risk_scores": _risk_scores(3)},
        headers=owner_headers,
    )
    assert response.status_code == 422


def test_missing_criterion_key_is_422(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id, proposal_id = _create_scoreable_proposal(
        client,
        owner_headers,
        vendor_membership_id,
        tenant_id=tenant_a,
        seeded_actors=seeded_actors,
        mongo_test_settings=mongo_test_settings,
    )
    response = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/economic-assessment",
        json={"commercial_scores": _full_scores(3)[:4], "risk_scores": _risk_scores(3)},
        headers=owner_headers,
    )
    assert response.status_code == 422


def test_internal_collaborator_cannot_write_economic_assessment(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id, proposal_id = _create_scoreable_proposal(
        client,
        owner_headers,
        vendor_membership_id,
        tenant_id=tenant_a,
        seeded_actors=seeded_actors,
        mongo_test_settings=mongo_test_settings,
    )
    collaborator_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "internal_collaborator")], mongo_test_settings
    )
    response = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/economic-assessment",
        json={"commercial_scores": _full_scores(3), "risk_scores": _risk_scores(3)},
        headers=collaborator_headers,
    )
    assert response.status_code == 403


def test_evaluator_economic_can_write_when_assigned_to_economic_section(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id, proposal_id = _create_scoreable_proposal(
        client,
        owner_headers,
        vendor_membership_id,
        tenant_id=tenant_a,
        seeded_actors=seeded_actors,
        mongo_test_settings=mongo_test_settings,
    )
    economic_membership_id = seeded_actors[(tenant_a, "evaluator_economic")]
    assignment = client.post(
        f"/api/v1/evaluations/{evaluation_id}/assignments",
        json={
            "dimension": "economic",
            "section": "economic",
            "evaluator_membership_id": economic_membership_id,
        },
        headers=owner_headers,
    )
    assert assignment.status_code == 201

    economic_headers = bearer_headers_for(economic_membership_id, mongo_test_settings)
    response = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/economic-assessment",
        json={"commercial_scores": _full_scores(4), "risk_scores": _risk_scores(4)},
        headers=economic_headers,
    )
    assert response.status_code == 200


def test_evaluator_economic_can_write_when_section_unassigned(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id, proposal_id = _create_scoreable_proposal(
        client,
        owner_headers,
        vendor_membership_id,
        tenant_id=tenant_a,
        seeded_actors=seeded_actors,
        mongo_test_settings=mongo_test_settings,
    )
    economic_membership_id = seeded_actors[(tenant_a, "evaluator_economic")]
    economic_headers = bearer_headers_for(economic_membership_id, mongo_test_settings)
    response = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/economic-assessment",
        json={"commercial_scores": _full_scores(4), "risk_scores": _risk_scores(4)},
        headers=economic_headers,
    )
    assert response.status_code == 200


def test_assignment_rejects_economic_section_other_than_the_fixed_sentinel(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Assignment economico invalido", "description": ""},
        headers=owner_headers,
    ).json()["id"]
    economic_membership_id = seeded_actors[(tenant_a, "evaluator_economic")]
    response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/assignments",
        json={
            "dimension": "economic",
            "section": "not-the-sentinel",
            "evaluator_membership_id": economic_membership_id,
        },
        headers=owner_headers,
    )
    assert response.status_code == 400


# --- economic-criteria-weights ---


def test_owner_updates_economic_criteria_weights(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Pesos economicos", "description": ""},
        headers=owner_headers,
    ).json()["id"]

    response = client.patch(
        f"/api/v1/evaluations/{evaluation_id}/economic-criteria-weights",
        json={
            "commercial": {
                "payment_terms": 40,
                "price_protection": 20,
                "contractual_flexibility": 20,
                "discounts_incentives": 10,
                "billing_transparency": 10,
            },
            "risk": {
                "variable_cost_exposure": 30,
                "increases_indexation": 25,
                "assumptions_exclusions": 20,
                "fx_fiscal_regulatory": 15,
                "exit_portability_lockin": 10,
            },
        },
        headers=owner_headers,
    )
    assert response.status_code == 200
    assert response.json()["economic_criteria_weights"]["commercial"]["payment_terms"] == 40


def test_economic_criteria_weights_not_summing_to_100_is_422(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Pesos invalidos", "description": ""},
        headers=owner_headers,
    ).json()["id"]

    response = client.patch(
        f"/api/v1/evaluations/{evaluation_id}/economic-criteria-weights",
        json={
            "commercial": {
                "payment_terms": 50,
                "price_protection": 20,
                "contractual_flexibility": 20,
                "discounts_incentives": 10,
                "billing_transparency": 10,
            },
            "risk": {
                "variable_cost_exposure": 30,
                "increases_indexation": 25,
                "assumptions_exclusions": 20,
                "fx_fiscal_regulatory": 15,
                "exit_portability_lockin": 10,
            },
        },
        headers=owner_headers,
    )
    assert response.status_code == 422


def test_non_owner_cannot_update_economic_criteria_weights(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Pesos no-owner", "description": ""},
        headers=owner_headers,
    ).json()["id"]
    economic_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluator_economic")], mongo_test_settings
    )
    response = client.patch(
        f"/api/v1/evaluations/{evaluation_id}/economic-criteria-weights",
        json={
            "commercial": {
                "payment_terms": 25,
                "price_protection": 25,
                "contractual_flexibility": 20,
                "discounts_incentives": 15,
                "billing_transparency": 15,
            },
            "risk": {
                "variable_cost_exposure": 30,
                "increases_indexation": 25,
                "assumptions_exclusions": 20,
                "fx_fiscal_regulatory": 15,
                "exit_portability_lockin": 10,
            },
        },
        headers=economic_headers,
    )
    assert response.status_code == 403


def test_weights_cannot_be_updated_after_draft(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id, _proposal_id = _create_scoreable_proposal(
        client,
        owner_headers,
        vendor_membership_id,
        tenant_id=tenant_a,
        seeded_actors=seeded_actors,
        mongo_test_settings=mongo_test_settings,
    )
    response = client.patch(
        f"/api/v1/evaluations/{evaluation_id}/economic-criteria-weights",
        json={
            "commercial": {
                "payment_terms": 25,
                "price_protection": 25,
                "contractual_flexibility": 20,
                "discounts_incentives": 15,
                "billing_transparency": 15,
            },
            "risk": {
                "variable_cost_exposure": 30,
                "increases_indexation": 25,
                "assumptions_exclusions": 20,
                "fx_fiscal_regulatory": 15,
                "exit_portability_lockin": 10,
            },
        },
        headers=owner_headers,
    )
    assert response.status_code == 409


def test_evaluation_snapshot_freezes_economic_criteria_weights(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    vendor_dev_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_dev_headers).json()["vendor_org_id"]
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Snapshot pesos", "description": ""},
        headers=owner_headers,
    ).json()["id"]
    client.patch(
        f"/api/v1/evaluations/{evaluation_id}/economic-criteria-weights",
        json={
            "commercial": {
                "payment_terms": 60,
                "price_protection": 10,
                "contractual_flexibility": 10,
                "discounts_incentives": 10,
                "billing_transparency": 10,
            },
            "risk": {
                "variable_cost_exposure": 30,
                "increases_indexation": 25,
                "assumptions_exclusions": 20,
                "fx_fiscal_regulatory": 15,
                "exit_portability_lockin": 10,
            },
        },
        headers=owner_headers,
    )
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "functional",
            "category": "Core",
            "title": "T",
            "description": "D",
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
            "title": "T2",
            "description": "D2",
            "priority": "important",
            "response_type": "text",
            "weight": 20.0,
            "required": False,
            "display_order": 2,
        },
        headers=owner_headers,
    )
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/vendors",
        json={"vendor_org_id": vendor_org_id},
        headers=owner_headers,
    )
    approver_membership_id = seeded_actors[(tenant_a, "approver")]
    approver_headers = bearer_headers_for(approver_membership_id, mongo_test_settings)
    approve_and_publish(
        client, owner_headers, approver_membership_id, approver_headers, evaluation_id
    )

    snapshot = client.get(f"/api/v1/evaluations/{evaluation_id}/snapshot", headers=owner_headers)
    assert snapshot.status_code == 200
    assert snapshot.json()["economic_criteria_weights"]["commercial"]["payment_terms"] == 60
