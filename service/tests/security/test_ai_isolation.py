import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from procurawise.ai.models import AIResponse, TokenUsage
from procurawise.ai.router import get_ai_provider
from procurawise.ai.service import build_ai_service
from procurawise.api.main import app
from procurawise.evaluations.models import Evaluation, Requirement
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.proposals.models import Proposal, ProposalAnswer, ProposalSnapshot, new_id
from procurawise.proposals.repository import ProposalRepository
from procurawise.shared.mongo import get_database
from tests.conftest import bearer_headers_for, tenant_ids
from tests.fakes.fake_ai_provider import FakeAIProvider

pytestmark = pytest.mark.docker


def _create_evaluation(client, owner_headers) -> str:
    created = client.post(
        "/api/v1/evaluations",
        json={"name": "RFP", "description": ""},
        headers=owner_headers,
    )
    assert created.status_code == 201
    return created.json()["id"]


def _valid_response() -> AIResponse:
    payload = {
        "candidates": [
            {
                "dimension": "functional",
                "category": "Reporting",
                "title": "Custom dashboards",
                "description": "Configurable dashboards for KPIs",
                "priority": "important",
                "response_type": "text",
                "weight": 5.0,
                "required": False,
                "buyer_guidance": "",
                "options": [],
                "rationale": "Matches the described reporting need",
                "sources": [],
            }
        ]
    }
    return AIResponse(
        raw_output=json.dumps(payload),
        parsed_output=payload,
        token_usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        model="gpt-4o-mini",
        latency_ms=500,
        finish_reason="stop",
    )


@pytest.fixture(autouse=True)
def _fake_ai_provider():
    fake = FakeAIProvider(responses=[_valid_response()])
    app.dependency_overrides[get_ai_provider] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_ai_provider, None)


def test_owner_of_other_tenant_gets_404_reading_job_status(
    client, seeded_actors, mongo_test_settings, _fake_ai_provider
) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    evaluation_a_id = _create_evaluation(client, owner_a_headers)
    triggered = client.post(
        f"/api/v1/evaluations/{evaluation_a_id}/ai/requirement-suggestions",
        json={"dimension": "functional", "description": "We need a reporting tool"},
        headers=owner_a_headers,
    )
    job_id = triggered.json()["job_id"]

    response = client.get(
        f"/api/v1/evaluations/{evaluation_a_id}/ai/requirement-suggestions/{job_id}",
        headers=owner_b_headers,
    )
    assert response.status_code == 404


def test_owner_of_other_tenant_cannot_trigger_on_foreign_evaluation(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    evaluation_a_id = _create_evaluation(client, owner_a_headers)

    response = client.post(
        f"/api/v1/evaluations/{evaluation_a_id}/ai/requirement-suggestions",
        json={"dimension": "functional", "description": "hijack attempt"},
        headers=owner_b_headers,
    )
    assert response.status_code == 404


def test_owner_of_other_tenant_cannot_accept_foreign_job_and_no_mutation_occurs(
    client, seeded_actors, mongo_test_settings, _fake_ai_provider
) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    evaluation_a_id = _create_evaluation(client, owner_a_headers)
    evaluation_b_id = _create_evaluation(client, owner_b_headers)
    triggered = client.post(
        f"/api/v1/evaluations/{evaluation_a_id}/ai/requirement-suggestions",
        json={"dimension": "functional", "description": "We need a reporting tool"},
        headers=owner_a_headers,
    )
    job_id = triggered.json()["job_id"]
    ai_service = build_ai_service(mongo_test_settings, _fake_ai_provider)
    ai_service.process_generation_job(
        tenant_a, job_id, dimension="functional", description="We need a reporting tool"
    )

    # tenant B references its own evaluation_id (never tenant A's) - the job
    # lookup must still 404 because the job itself belongs to tenant A.
    response = client.post(
        f"/api/v1/evaluations/{evaluation_b_id}/ai/requirement-suggestions/{job_id}/accept",
        json={"candidate_indices": [0]},
        headers=owner_b_headers,
    )
    assert response.status_code == 404

    evaluation_a = client.get(f"/api/v1/evaluations/{evaluation_a_id}", headers=owner_a_headers)
    assert evaluation_a.json()["requirements"] == []
    evaluation_b = client.get(f"/api/v1/evaluations/{evaluation_b_id}", headers=owner_b_headers)
    assert evaluation_b.json()["requirements"] == []


def _valid_score_response(requirement_id: str) -> AIResponse:
    payload = {
        "candidates": [
            {
                "requirement_id": requirement_id,
                "suggested_score": 4,
                "risk_flags": [],
                "rationale": "ok",
            }
        ]
    }
    return AIResponse(
        raw_output=json.dumps(payload),
        parsed_output=payload,
        token_usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        model="gpt-4o-mini",
        latency_ms=500,
        finish_reason="stop",
    )


def _create_evaluating_proposal(mongo_test_settings, tenant_id: str, owner_membership_id: str):
    """Fase 18 (ADR 0022): same direct-repository shortcut as
    test_ai_score_suggestion_service.py - only a vendor_org_id string is
    needed for the snapshot, no real vendor Membership (tenant_b in this
    seed has none)."""
    db = get_database(mongo_test_settings)
    evaluations = EvaluationRepository(db)
    proposals = ProposalRepository(db)

    requirement = Requirement.create(
        dimension="functional",
        category="Core",
        title="Soporta SSO",
        description="d",
        priority="important",
        response_type="text",
        weight=40.0,
        required=False,
        display_order=1,
    )
    evaluation = Evaluation.create(tenant_id, "RFP", "", owner_membership_id)
    evaluation = replace(evaluation, requirements=[requirement], status="evaluating")
    evaluations.insert(tenant_id, evaluation.to_document())

    now = datetime.now(UTC)
    snapshot = ProposalSnapshot(
        snapshot_id=new_id(),
        taken_at=now,
        evaluation_id=evaluation.id,
        evaluation_name=evaluation.name,
        vendor_org_id="vendor-org-1",
        vendor_org_name="Vendor",
        requirements=[requirement],
        answers=[
            ProposalAnswer(
                requirement_id=requirement.id,
                value="Si, soportamos SSO via SAML.",
                vendor_comment=None,
                updated_at=now,
            )
        ],
        submitted_by_membership_id="vendor-membership",
        submitted_at=now,
        document_ids=[],
        cost_items=[],
        tco_result=None,
    )
    proposal = Proposal.create(
        tenant_id=tenant_id, evaluation_id=evaluation.id, vendor_org_id="vendor-org-1"
    )
    proposal = replace(proposal, status="submitted", snapshots=[snapshot], answers=snapshot.answers)
    proposals.insert(tenant_id, proposal.to_document())
    return evaluation.id, proposal.id, requirement.id


def test_owner_of_other_tenant_gets_404_reading_score_suggestion_job_status(
    client, seeded_actors, mongo_test_settings, _fake_ai_provider
) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    evaluation_a_id, proposal_a_id, requirement_id = _create_evaluating_proposal(
        mongo_test_settings, tenant_a, seeded_actors[(tenant_a, "evaluation_owner")]
    )
    _fake_ai_provider.responses = [_valid_score_response(requirement_id)]
    triggered = client.post(
        f"/api/v1/evaluations/{evaluation_a_id}/proposals/{proposal_a_id}/ai/score-suggestions",
        json={},
        headers=owner_a_headers,
    )
    job_id = triggered.json()["job_id"]

    response = client.get(
        f"/api/v1/evaluations/{evaluation_a_id}/proposals/{proposal_a_id}"
        f"/ai/score-suggestions/{job_id}",
        headers=owner_b_headers,
    )
    assert response.status_code == 404


def test_owner_of_other_tenant_cannot_trigger_on_foreign_proposal(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    evaluation_a_id, proposal_a_id, _requirement_id = _create_evaluating_proposal(
        mongo_test_settings, tenant_a, seeded_actors[(tenant_a, "evaluation_owner")]
    )

    response = client.post(
        f"/api/v1/evaluations/{evaluation_a_id}/proposals/{proposal_a_id}/ai/score-suggestions",
        json={},
        headers=owner_b_headers,
    )
    assert response.status_code == 404


def test_owner_of_other_tenant_cannot_read_or_leak_a_foreign_job_via_a_second_proposal(
    client, seeded_actors, mongo_test_settings, _fake_ai_provider
) -> None:
    """The job itself belongs to tenant A's proposal - referencing tenant B's
    own (unrelated) evaluation/proposal ids alongside tenant A's real job_id
    must still 404, never leak tenant A's candidates."""
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    evaluation_a_id, proposal_a_id, requirement_id = _create_evaluating_proposal(
        mongo_test_settings, tenant_a, seeded_actors[(tenant_a, "evaluation_owner")]
    )
    evaluation_b_id, proposal_b_id, _req_b = _create_evaluating_proposal(
        mongo_test_settings, tenant_b, seeded_actors[(tenant_b, "evaluation_owner")]
    )
    _fake_ai_provider.responses = [_valid_score_response(requirement_id)]
    triggered = client.post(
        f"/api/v1/evaluations/{evaluation_a_id}/proposals/{proposal_a_id}/ai/score-suggestions",
        json={},
        headers=bearer_headers_for(
            seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
        ),
    )
    job_id = triggered.json()["job_id"]

    response = client.get(
        f"/api/v1/evaluations/{evaluation_b_id}/proposals/{proposal_b_id}"
        f"/ai/score-suggestions/{job_id}",
        headers=owner_b_headers,
    )
    assert response.status_code == 404
