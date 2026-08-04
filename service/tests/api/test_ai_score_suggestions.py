import json

import pytest

from procurawise.ai.models import AIResponse, TokenUsage
from procurawise.ai.router import get_ai_provider
from procurawise.ai.service import build_ai_service
from procurawise.api.main import app
from procurawise.assignments.models import Assignment
from procurawise.assignments.repository import AssignmentRepository
from procurawise.identity.dev_provider import DEV_ACTOR_HEADER
from procurawise.shared.mongo import get_database
from tests.conftest import (
    approve_and_publish,
    bearer_headers_for,
    unique_actor_by_role,
    vendor_bearer_headers_for,
)
from tests.fakes.fake_ai_provider import FakeAIProvider

pytestmark = pytest.mark.docker


def _valid_response(requirement_id: str, suggested_score: int = 4) -> AIResponse:
    payload = {
        "candidates": [
            {
                "requirement_id": requirement_id,
                "suggested_score": suggested_score,
                "risk_flags": ["missing_evidence"],
                "rationale": "La respuesta no incluye evidencia suficiente.",
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
    fake = FakeAIProvider()
    app.dependency_overrides[get_ai_provider] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_ai_provider, None)


def _process_job(mongo_test_settings, fake_provider, tenant_id, job_id, requirement_ids):
    ai_service = build_ai_service(mongo_test_settings, fake_provider)
    ai_service.process_score_suggestion_job(tenant_id, job_id, requirement_ids=requirement_ids)


def _submitted_proposal(client, seeded_actors, mongo_test_settings):
    """Same shape as test_scoring_audit_instrumentation.py's helper: one
    evaluation in `evaluating` status, one submitted proposal, a functional
    and a technical requirement, both answered."""
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    vendor_dev_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_dev_headers).json()["vendor_org_id"]
    vendor_headers = vendor_bearer_headers_for(vendor_membership_id, mongo_test_settings)

    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Scoring AI RFP", "description": ""},
        headers=owner_headers,
    ).json()["id"]

    functional_id = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "functional",
            "category": "Core",
            "title": "Soporta SSO",
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
            "title": "Uptime SLA",
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
        json={"value": "Si, soportamos SSO via SAML.", "expected_version": 1},
        headers=vendor_headers,
    )
    client.put(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/answers/{technical_id}",
        json={"value": "99.9% mensual.", "expected_version": 2},
        headers=vendor_headers,
    )
    client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/submit",
        json={"expected_version": 3},
        headers=vendor_headers,
    )
    client.post(f"/api/v1/evaluations/{evaluation_id}/start-evaluation", headers=owner_headers)

    return {
        "tenant_id": tenant_a,
        "evaluation_id": evaluation_id,
        "proposal_id": proposal_id,
        "functional_id": functional_id,
        "technical_id": technical_id,
        "owner_headers": owner_headers,
    }


def test_trigger_returns_202_with_job_id_and_status_url(
    client, seeded_actors, mongo_test_settings
) -> None:
    ctx = _submitted_proposal(client, seeded_actors, mongo_test_settings)

    response = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/proposals/{ctx['proposal_id']}"
        "/ai/score-suggestions",
        json={},
        headers=ctx["owner_headers"],
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"]
    assert body["status_url"].endswith(f"/ai/score-suggestions/{body['job_id']}")


def test_status_transitions_from_queued_to_succeeded_after_worker_processes(
    client, seeded_actors, mongo_test_settings, _fake_ai_provider
) -> None:
    ctx = _submitted_proposal(client, seeded_actors, mongo_test_settings)
    triggered = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/proposals/{ctx['proposal_id']}"
        "/ai/score-suggestions",
        json={},
        headers=ctx["owner_headers"],
    )
    job_id = triggered.json()["job_id"]

    queued = client.get(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/proposals/{ctx['proposal_id']}"
        f"/ai/score-suggestions/{job_id}",
        headers=ctx["owner_headers"],
    )
    assert queued.json()["status"] == "queued"

    _fake_ai_provider.responses = [_valid_response(ctx["functional_id"])]
    _process_job(
        mongo_test_settings,
        _fake_ai_provider,
        ctx["tenant_id"],
        job_id,
        [ctx["functional_id"], ctx["technical_id"]],
    )

    succeeded = client.get(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/proposals/{ctx['proposal_id']}"
        f"/ai/score-suggestions/{job_id}",
        headers=ctx["owner_headers"],
    )
    body = succeeded.json()
    assert body["status"] == "succeeded"
    assert len(body["candidates"]) == 1
    assert body["candidates"][0]["requirement_id"] == ctx["functional_id"]
    assert body["candidates"][0]["suggested_score"] == 4
    assert body["model"] == "gpt-4o-mini"
    assert body["token_usage"]["total_tokens"] == 150


def test_accepting_a_suggestion_unchanged_records_ai_decision_accepted(
    client, seeded_actors, mongo_test_settings, mongo_test_db, _fake_ai_provider
) -> None:
    ctx = _submitted_proposal(client, seeded_actors, mongo_test_settings)
    triggered = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/proposals/{ctx['proposal_id']}"
        "/ai/score-suggestions",
        json={},
        headers=ctx["owner_headers"],
    )
    job_id = triggered.json()["job_id"]
    _fake_ai_provider.responses = [_valid_response(ctx["functional_id"], suggested_score=4)]
    _process_job(
        mongo_test_settings,
        _fake_ai_provider,
        ctx["tenant_id"],
        job_id,
        [ctx["functional_id"]],
    )

    # "Aceptar tal cual": the evaluator submits exactly the suggested score
    # through the pre-existing scoring endpoint - no new write path.
    written = client.put(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/proposals/{ctx['proposal_id']}"
        f"/scores/{ctx['functional_id']}",
        json={"score": 4, "comment": None, "version": None, "source_ai_execution_id": job_id},
        headers=ctx["owner_headers"],
    )
    assert written.status_code == 200
    assert written.json()["source_ai_execution_id"] == job_id

    event = mongo_test_db["audit_events"].find_one(
        {"action": "score_created", "resource_id": written.json()["id"]}
    )
    assert event is not None
    assert event["metadata"]["ai_decision"] == "accepted"


def test_modifying_a_suggestion_records_ai_decision_modified(
    client, seeded_actors, mongo_test_settings, mongo_test_db, _fake_ai_provider
) -> None:
    ctx = _submitted_proposal(client, seeded_actors, mongo_test_settings)
    triggered = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/proposals/{ctx['proposal_id']}"
        "/ai/score-suggestions",
        json={},
        headers=ctx["owner_headers"],
    )
    job_id = triggered.json()["job_id"]
    _fake_ai_provider.responses = [_valid_response(ctx["functional_id"], suggested_score=4)]
    _process_job(
        mongo_test_settings,
        _fake_ai_provider,
        ctx["tenant_id"],
        job_id,
        [ctx["functional_id"]],
    )

    # The evaluator disagrees with the suggested 4 and submits a 2 instead.
    written = client.put(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/proposals/{ctx['proposal_id']}"
        f"/scores/{ctx['functional_id']}",
        json={
            "score": 2,
            "comment": "No cubre el caso de MFA",
            "version": None,
            "source_ai_execution_id": job_id,
        },
        headers=ctx["owner_headers"],
    )
    assert written.status_code == 200
    assert written.json()["score"] == 2

    event = mongo_test_db["audit_events"].find_one(
        {"action": "score_created", "resource_id": written.json()["id"]}
    )
    assert event is not None
    assert event["metadata"]["ai_decision"] == "modified"
    # The free-text comment never enters the audit trail (pre-existing rule,
    # unaffected by ai_decision).
    assert "MFA" not in str(event)


def test_manual_score_without_source_ai_execution_id_has_no_ai_decision(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    ctx = _submitted_proposal(client, seeded_actors, mongo_test_settings)

    written = client.put(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/proposals/{ctx['proposal_id']}"
        f"/scores/{ctx['functional_id']}",
        json={"score": 5, "comment": None, "version": None},
        headers=ctx["owner_headers"],
    )
    assert written.status_code == 200
    assert written.json()["source_ai_execution_id"] is None

    event = mongo_test_db["audit_events"].find_one(
        {"action": "score_created", "resource_id": written.json()["id"]}
    )
    assert event is not None
    assert "ai_decision" not in event["metadata"]


def test_non_assigned_evaluator_cannot_trigger_for_an_assigned_section(
    client, seeded_actors, mongo_test_settings
) -> None:
    ctx = _submitted_proposal(client, seeded_actors, mongo_test_settings)
    tenant_a = ctx["tenant_id"]
    evaluator_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluator_functional")], mongo_test_settings
    )

    # Inserted directly (not via POST .../assignments, whose role-match
    # validation would reject any seeded membership other than the actor's
    # own evaluator_functional) - the section only needs to be assigned to
    # *someone else*, real or not, for enforce_section_assignment to reject
    # this evaluator (same technique as test_ai_score_suggestion_service.py).
    assignments = AssignmentRepository(get_database(mongo_test_settings))
    assignment = Assignment.create(
        tenant_a,
        ctx["evaluation_id"],
        "functional",
        "Core",
        "someone-else-membership",
        seeded_actors[(tenant_a, "evaluation_owner")],
    )
    assignments.insert(tenant_a, assignment.to_document())

    response = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/proposals/{ctx['proposal_id']}"
        "/ai/score-suggestions",
        json={"requirement_ids": [ctx["functional_id"]]},
        headers=evaluator_headers,
    )
    assert response.status_code == 403


def test_trigger_rejected_when_proposal_does_not_exist(
    client, seeded_actors, mongo_test_settings
) -> None:
    ctx = _submitted_proposal(client, seeded_actors, mongo_test_settings)

    response = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/proposals/does-not-exist/ai/score-suggestions",
        json={},
        headers=ctx["owner_headers"],
    )
    assert response.status_code == 404


def test_unknown_job_id_is_404(client, seeded_actors, mongo_test_settings) -> None:
    ctx = _submitted_proposal(client, seeded_actors, mongo_test_settings)

    response = client.get(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/proposals/{ctx['proposal_id']}"
        "/ai/score-suggestions/does-not-exist",
        headers=ctx["owner_headers"],
    )
    assert response.status_code == 404
