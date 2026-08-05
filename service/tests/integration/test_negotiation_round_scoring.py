"""Fase 21 acceptance criterion (backlog.md fila 21): "Modificar una
respuesta invalida su score; TCO nunca mezcla costos entre versiones."
This file proves the read-side score invalidation/fallback
(ScoringService._scores_for_current_snapshot) and the TCO-never-mixed
guarantee directly against get_results()/complete_evaluation()."""

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


def _max_economic_assessment_body() -> dict:
    return {
        "commercial_scores": [
            {"criterion_key": k, "score": 5, "comment": "Excelente"} for k in _COMMERCIAL_KEYS
        ],
        "risk_scores": [
            {"criterion_key": k, "score": 5, "comment": "Excelente"} for k in _RISK_KEYS
        ],
    }


def _submit_economic_assessment(client, ctx):
    response = client.put(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/proposals/{ctx['proposal_id']}/economic-assessment",
        json=_max_economic_assessment_body(),
        headers=ctx["owner_headers"],
    )
    assert response.status_code == 200


def _setup_reopened_proposal(client, seeded_actors, mongo_test_settings):
    """One evaluation, 1 functional (weight 40) + 1 technical (weight 20)
    requirement, one proposal fully scored in Ronda 0, then reopened into
    Ronda 1 without any edits yet - the caller decides which answer (if
    any) to modify before resubmitting."""
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    vendor_dev_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_dev_headers).json()["vendor_org_id"]
    vendor_headers = vendor_bearer_headers_for(vendor_membership_id, mongo_test_settings)

    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Negotiation scoring RFP", "description": ""},
        headers=owner_headers,
    ).json()["id"]
    functional_id = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "functional",
            "category": "Core",
            "title": "Req funcional",
            "description": "d",
            "priority": "important",
            "response_type": "text",
            "weight": 40.0,
            "required": False,
            "display_order": 1,
        },
        headers=owner_headers,
    ).json()["id"]
    technical_id = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "technical",
            "category": "Core",
            "title": "Req tecnico",
            "description": "d",
            "priority": "important",
            "response_type": "text",
            "weight": 20.0,
            "required": False,
            "display_order": 2,
        },
        headers=owner_headers,
    ).json()["id"]
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

    client.put(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/answers/{functional_id}",
        json={"value": "Respuesta funcional v0.", "expected_version": 1},
        headers=vendor_headers,
    )
    client.put(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/answers/{technical_id}",
        json={"value": "Respuesta tecnica v0.", "expected_version": 2},
        headers=vendor_headers,
    )
    cost_item = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/cost-items",
        json={
            "concept": "Licencia anual",
            "category": "recurring",
            "billing_unit": "usuario",
            "quantity": "10",
            "unit_price": "100",
            "currency": "MXN",
            "frequency_per_year": "1",
            "year_start": 1,
            "year_end": 1,
            "cost_type": "recurring",
            "expected_version": 3,
        },
        headers=vendor_headers,
    )
    client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/submit",
        json={"expected_version": cost_item.json()["version"]},
        headers=vendor_headers,
    )
    client.post(f"/api/v1/evaluations/{evaluation_id}/start-evaluation", headers=owner_headers)

    # Ronda 0: score both requirements fully (owner, unassigned sections).
    client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/scores/{functional_id}",
        json={"score": 4, "comment": None},
        headers=owner_headers,
    )
    client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/scores/{technical_id}",
        json={"score": 5, "comment": None},
        headers=owner_headers,
    )
    economic_assessment = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/economic-assessment",
        json=_max_economic_assessment_body(),
        headers=owner_headers,
    )
    assert economic_assessment.status_code == 200

    reopened = client.post(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/reopen",
        json={"reason": "Negociacion", "response_deadline": "2030-06-01T00:00:00Z"},
        headers=owner_headers,
    )
    assert reopened.status_code == 200

    return {
        "evaluation_id": evaluation_id,
        "proposal_id": proposal_id,
        "functional_id": functional_id,
        "technical_id": technical_id,
        "owner_headers": owner_headers,
        "vendor_headers": vendor_headers,
        "reopen_version": reopened.json()["version"],
    }


def _resubmit(client, ctx, version: int):
    submitted = client.post(
        f"/api/v1/vendor-portal/proposals/{ctx['proposal_id']}/submit",
        json={"expected_version": version},
        headers=ctx["vendor_headers"],
    )
    assert submitted.status_code == 200
    client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/start-evaluation", headers=ctx["owner_headers"]
    )


def _results(client, ctx):
    response = client.get(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/results", headers=ctx["owner_headers"]
    )
    assert response.status_code == 200
    return response.json()


def test_unmodified_answers_keep_their_previous_round_score_via_fallback(
    client, seeded_actors, mongo_test_settings
) -> None:
    ctx = _setup_reopened_proposal(client, seeded_actors, mongo_test_settings)
    # Resubmit Ronda 1 with zero edits - both answers stay "inherited".
    _resubmit(client, ctx, ctx["reopen_version"])

    body = _results(client, ctx)
    # Functional/technical scores carry forward via fallback, but the
    # EconomicAssessment never carries over across rounds (plan Fase 21 §9
    # decision #4) - it's scoped to Ronda 0's snapshot_id, so Ronda 1 starts
    # unassessed and scoring_status stays "incomplete" until reassessed.
    assert body["scoring_status"] == "incomplete"
    [proposal_result] = body["proposals"]
    assert proposal_result["functional"]["earned_points"] == 32.0  # (4/5)*40
    assert proposal_result["technical"]["earned_points"] == 20.0  # (5/5)*20
    assert proposal_result["economic"]["status"] == "not_available"
    scored_ids = {s["requirement_id"] for s in proposal_result["scores"]}
    assert scored_ids == {ctx["functional_id"], ctx["technical_id"]}

    _submit_economic_assessment(client, ctx)
    body_after_reassessment = _results(client, ctx)
    assert body_after_reassessment["scoring_status"] == "complete"


def test_modified_answer_invalidates_its_score_until_rescored(
    client, seeded_actors, mongo_test_settings
) -> None:
    ctx = _setup_reopened_proposal(client, seeded_actors, mongo_test_settings)

    edited = client.put(
        f"/api/v1/vendor-portal/proposals/{ctx['proposal_id']}/answers/{ctx['functional_id']}",
        json={
            "value": "Respuesta funcional v1 (mejorada).",
            "expected_version": ctx["reopen_version"],
        },
        headers=ctx["vendor_headers"],
    )
    assert edited.status_code == 200
    _resubmit(client, ctx, edited.json()["version"])

    body = _results(client, ctx)
    assert body["scoring_status"] == "incomplete"
    [proposal_result] = body["proposals"]
    scored_ids = {s["requirement_id"] for s in proposal_result["scores"]}
    # The modified requirement's Ronda 0 score no longer counts - only the
    # unmodified (still "inherited") technical requirement carries forward.
    assert scored_ids == {ctx["technical_id"]}
    assert proposal_result["technical"]["earned_points"] == 20.0
    assert proposal_result["functional"]["earned_points"] == 0.0

    # The EconomicAssessment never carries over either (decision #4) - both
    # gaps must close before complete_evaluation() is allowed.
    _submit_economic_assessment(client, ctx)

    complete_attempt = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/complete", headers=ctx["owner_headers"]
    )
    assert complete_attempt.status_code == 400

    rescored = client.put(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/proposals/{ctx['proposal_id']}/scores/{ctx['functional_id']}",
        json={"score": 3, "comment": None},
        headers=ctx["owner_headers"],
    )
    assert rescored.status_code == 200

    body_after_rescoring = _results(client, ctx)
    assert body_after_rescoring["scoring_status"] == "complete"
    [proposal_result_after] = body_after_rescoring["proposals"]
    assert proposal_result_after["functional"]["earned_points"] == 24.0  # (3/5)*40


def test_tco_never_mixes_costs_between_rounds(client, seeded_actors, mongo_test_settings) -> None:
    ctx = _setup_reopened_proposal(client, seeded_actors, mongo_test_settings)

    detail = client.get(
        f"/api/v1/vendor-portal/proposals/{ctx['proposal_id']}", headers=ctx["vendor_headers"]
    ).json()
    cost_item_id = detail["cost_items"][0]["id"]
    updated = client.put(
        f"/api/v1/vendor-portal/proposals/{ctx['proposal_id']}/cost-items/{cost_item_id}",
        json={"quantity": "20", "expected_version": ctx["reopen_version"]},
        headers=ctx["vendor_headers"],
    )
    assert updated.status_code == 200
    _resubmit(client, ctx, updated.json()["version"])

    proposal_detail = client.get(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/proposals/{ctx['proposal_id']}",
        headers=ctx["owner_headers"],
    ).json()
    snapshots = proposal_detail["snapshots"]
    assert len(snapshots) == 2
    # Ronda 0's frozen TCO/cost items are untouched by the Ronda 1 edit -
    # each snapshot carries its own independent tco_result (plan §12.7/R10).
    assert snapshots[0]["tco_result"]["grand_total"] == "1000.00"  # frozen 10 * 100
    assert snapshots[0]["cost_items"][0]["quantity"] == "10"
    assert snapshots[1]["tco_result"]["grand_total"] == "2000.00"  # frozen 20 * 100
    assert snapshots[1]["cost_items"][0]["quantity"] == "20"
    assert snapshots[1]["cost_items"][0]["status"] == "modified"
    assert snapshots[1]["cost_items"][0]["source_proposal_version"] == 0

    tco_round1 = client.get(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/proposals/{ctx['proposal_id']}/tco",
        headers=ctx["owner_headers"],
    )
    assert tco_round1.status_code == 200
    assert tco_round1.json()["grand_total"] == "2000.00"  # matches the current (round 1) snapshot
