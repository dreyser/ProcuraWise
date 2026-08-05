import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from procurawise.ai.models import AIResponse, TokenUsage
from procurawise.ai.service import build_ai_service
from procurawise.assignments.models import Assignment
from procurawise.assignments.repository import AssignmentRepository
from procurawise.evaluations.models import Evaluation, Requirement
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.repository import MembershipRepository, TenantRepository, UserRepository
from procurawise.identity.service import IdentityService
from procurawise.proposals.models import Proposal, ProposalAnswer, ProposalSnapshot, new_id
from procurawise.proposals.repository import ProposalRepository
from procurawise.scoring.exceptions import (
    RequirementNotInSnapshotError,
    ScoringPreconditionError,
    SectionNotAssignedToActorError,
)
from procurawise.shared.context import ActorContext
from procurawise.shared.mongo import get_database
from tests.conftest import unique_actor_by_role
from tests.fakes.fake_ai_provider import FakeAIProvider

pytestmark = pytest.mark.docker


@pytest.fixture(autouse=True)
def _clean(mongo_test_db):
    yield
    mongo_test_db["ai_executions"].delete_many({})
    mongo_test_db["evaluations"].delete_many({})
    mongo_test_db["proposals"].delete_many({})
    mongo_test_db["assignments"].delete_many({})
    mongo_test_db["audit_events"].delete_many({})


def _db(settings):
    return get_database(settings)


def _actor(mongo_test_settings, membership_id: str) -> ActorContext:
    db = _db(mongo_test_settings)
    identity_service = IdentityService(
        tenants=TenantRepository(db), users=UserRepository(db), memberships=MembershipRepository(db)
    )
    return identity_service.resolve_actor_context(membership_id)


def _create_evaluating_proposal(
    mongo_test_settings, tenant_id: str, vendor_org_id: str, owner_membership_id: str
) -> tuple[str, str, str, str]:
    """Returns (evaluation_id, proposal_id, functional_requirement_id,
    technical_requirement_id). Bypasses the full wizard/approval/submit
    workflow (same precedent as qna's _create_collecting_proposal) - targets
    AIService.request_score_suggestion/process_score_suggestion_job
    directly, not the HTTP surface (that's covered in tests/api, Block 4)."""
    db = _db(mongo_test_settings)
    evaluations = EvaluationRepository(db)
    proposals = ProposalRepository(db)

    functional_req = Requirement.create(
        dimension="functional",
        category="Core",
        title="Soporta SSO",
        description="Debe soportar SSO via SAML o OIDC.",
        priority="important",
        response_type="text",
        weight=40.0,
        required=False,
        display_order=1,
    )
    technical_req = Requirement.create(
        dimension="technical",
        category="Core",
        title="Uptime SLA",
        description="SLA de disponibilidad mensual.",
        priority="important",
        response_type="text",
        weight=20.0,
        required=False,
        display_order=2,
    )
    evaluation = Evaluation.create(tenant_id, "RFP asistido por IA", "", owner_membership_id)
    evaluation = replace(
        evaluation, requirements=[functional_req, technical_req], status="evaluating"
    )
    evaluations.insert(tenant_id, evaluation.to_document())

    now = datetime.now(UTC)
    snapshot = ProposalSnapshot(
        snapshot_id=new_id(),
        taken_at=now,
        evaluation_id=evaluation.id,
        evaluation_name=evaluation.name,
        vendor_org_id=vendor_org_id,
        vendor_org_name="Vendor",
        requirements=[functional_req, technical_req],
        answers=[
            ProposalAnswer(
                requirement_id=functional_req.id,
                value="Si, soportamos SSO via SAML.",
                vendor_comment=None,
                updated_at=now,
            ),
            ProposalAnswer(
                requirement_id=technical_req.id,
                value="99.9% mensual.",
                vendor_comment=None,
                updated_at=now,
            ),
        ],
        submitted_by_membership_id="vendor-membership",
        submitted_at=now,
        document_ids=[],
        cost_items=[],
        tco_result=None,
    )
    proposal = Proposal.create(
        tenant_id=tenant_id, evaluation_id=evaluation.id, vendor_org_id=vendor_org_id
    )
    proposal = replace(proposal, status="submitted", snapshots=[snapshot], answers=snapshot.answers)
    proposals.insert(tenant_id, proposal.to_document())
    return evaluation.id, proposal.id, functional_req.id, technical_req.id


def _valid_score_response(requirement_ids: list[str]) -> AIResponse:
    payload = {
        "candidates": [
            {
                "requirement_id": rid,
                "suggested_score": 4,
                "risk_flags": [],
                "rationale": "Respuesta clara y completa.",
            }
            for rid in requirement_ids
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


def _malformed_response() -> AIResponse:
    payload = {"candidates": [{"rationale": "missing every other required field"}]}
    return AIResponse(
        raw_output=json.dumps(payload),
        parsed_output=payload,
        token_usage=TokenUsage(prompt_tokens=80, completion_tokens=20, total_tokens=100),
        model="gpt-4o-mini",
        latency_ms=300,
        finish_reason="stop",
    )


def _response_with_foreign_requirement_id(real_id: str) -> AIResponse:
    payload = {
        "candidates": [
            {
                "requirement_id": real_id,
                "suggested_score": 3,
                "risk_flags": ["missing_evidence"],
                "rationale": "ok",
            },
            {
                "requirement_id": "invented-id-not-in-snapshot",
                "suggested_score": 5,
                "risk_flags": [],
                "rationale": "ok",
            },
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


def test_request_and_process_score_suggestion_succeeds_for_all_eligible_requirements(
    mongo_test_settings, seeded_actors
) -> None:
    # "evaluation_owner" is not unique across the seed (both tenants have
    # one) - derive tenant_id from "vendor_contact" (unique, tenant_a only)
    # instead, same precedent as test_scoring_audit_instrumentation.py.
    tenant_id, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_membership_id = seeded_actors[(tenant_id, "evaluation_owner")]
    vendor_org_id = _actor(mongo_test_settings, vendor_membership_id).vendor_org_id
    assert vendor_org_id is not None
    actor = _actor(mongo_test_settings, owner_membership_id)

    evaluation_id, proposal_id, functional_id, technical_id = _create_evaluating_proposal(
        mongo_test_settings, tenant_id, vendor_org_id, owner_membership_id
    )
    fake_provider = FakeAIProvider(responses=[_valid_score_response([functional_id, technical_id])])
    service = build_ai_service(mongo_test_settings, fake_provider)

    execution = service.request_score_suggestion(
        tenant_id, evaluation_id, proposal_id, [], actor=actor
    )
    assert execution.proposal_id == proposal_id
    assert execution.use_case == "score_suggestion"

    service.process_score_suggestion_job(
        tenant_id, execution.id, requirement_ids=[functional_id, technical_id]
    )

    result = service.get_score_suggestion_execution(
        tenant_id, evaluation_id, proposal_id, execution.id
    )
    assert result.status == "succeeded"
    assert result.candidates is not None
    assert {c["requirement_id"] for c in result.candidates} == {functional_id, technical_id}


def test_score_suggestion_retries_once_on_invalid_json_then_succeeds(
    mongo_test_settings, seeded_actors
) -> None:
    # "evaluation_owner" is not unique across the seed (both tenants have
    # one) - derive tenant_id from "vendor_contact" (unique, tenant_a only)
    # instead, same precedent as test_scoring_audit_instrumentation.py.
    tenant_id, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_membership_id = seeded_actors[(tenant_id, "evaluation_owner")]
    vendor_org_id = _actor(mongo_test_settings, vendor_membership_id).vendor_org_id
    assert vendor_org_id is not None
    actor = _actor(mongo_test_settings, owner_membership_id)

    evaluation_id, proposal_id, functional_id, technical_id = _create_evaluating_proposal(
        mongo_test_settings, tenant_id, vendor_org_id, owner_membership_id
    )
    fake_provider = FakeAIProvider(
        responses=[_malformed_response(), _valid_score_response([functional_id, technical_id])]
    )
    service = build_ai_service(mongo_test_settings, fake_provider)
    execution = service.request_score_suggestion(
        tenant_id, evaluation_id, proposal_id, [], actor=actor
    )
    service.process_score_suggestion_job(
        tenant_id, execution.id, requirement_ids=[functional_id, technical_id]
    )

    result = service.get_score_suggestion_execution(
        tenant_id, evaluation_id, proposal_id, execution.id
    )
    assert result.status == "succeeded"
    assert len(fake_provider.calls) == 2
    assert result.token_usage is not None
    assert result.token_usage.total_tokens == 100 + 150


def test_score_suggestion_drops_candidate_with_foreign_requirement_id(
    mongo_test_settings, seeded_actors
) -> None:
    # "evaluation_owner" is not unique across the seed (both tenants have
    # one) - derive tenant_id from "vendor_contact" (unique, tenant_a only)
    # instead, same precedent as test_scoring_audit_instrumentation.py.
    tenant_id, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_membership_id = seeded_actors[(tenant_id, "evaluation_owner")]
    vendor_org_id = _actor(mongo_test_settings, vendor_membership_id).vendor_org_id
    assert vendor_org_id is not None
    actor = _actor(mongo_test_settings, owner_membership_id)

    evaluation_id, proposal_id, functional_id, _technical_id = _create_evaluating_proposal(
        mongo_test_settings, tenant_id, vendor_org_id, owner_membership_id
    )
    fake_provider = FakeAIProvider(responses=[_response_with_foreign_requirement_id(functional_id)])
    service = build_ai_service(mongo_test_settings, fake_provider)
    execution = service.request_score_suggestion(
        tenant_id, evaluation_id, proposal_id, [functional_id], actor=actor
    )
    service.process_score_suggestion_job(tenant_id, execution.id, requirement_ids=[functional_id])

    result = service.get_score_suggestion_execution(
        tenant_id, evaluation_id, proposal_id, execution.id
    )
    assert result.status == "succeeded"
    assert result.candidates is not None
    assert len(result.candidates) == 1
    assert result.candidates[0]["requirement_id"] == functional_id


def test_request_rejected_when_evaluation_not_evaluating(
    mongo_test_settings, seeded_actors
) -> None:
    # "evaluation_owner" is not unique across the seed (both tenants have
    # one) - derive tenant_id from "vendor_contact" (unique, tenant_a only)
    # instead, same precedent as test_scoring_audit_instrumentation.py.
    tenant_id, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_membership_id = seeded_actors[(tenant_id, "evaluation_owner")]
    vendor_org_id = _actor(mongo_test_settings, vendor_membership_id).vendor_org_id
    assert vendor_org_id is not None
    actor = _actor(mongo_test_settings, owner_membership_id)

    evaluation_id, proposal_id, _functional_id, _technical_id = _create_evaluating_proposal(
        mongo_test_settings, tenant_id, vendor_org_id, owner_membership_id
    )
    db = _db(mongo_test_settings)
    db["evaluations"].update_one(
        {"_id": evaluation_id}, {"$set": {"status": "collecting_responses"}}
    )

    service = build_ai_service(mongo_test_settings, FakeAIProvider())
    with pytest.raises(ScoringPreconditionError):
        service.request_score_suggestion(tenant_id, evaluation_id, proposal_id, [], actor=actor)


def test_request_rejected_when_explicit_requirement_id_not_in_snapshot(
    mongo_test_settings, seeded_actors
) -> None:
    # "evaluation_owner" is not unique across the seed (both tenants have
    # one) - derive tenant_id from "vendor_contact" (unique, tenant_a only)
    # instead, same precedent as test_scoring_audit_instrumentation.py.
    tenant_id, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_membership_id = seeded_actors[(tenant_id, "evaluation_owner")]
    vendor_org_id = _actor(mongo_test_settings, vendor_membership_id).vendor_org_id
    assert vendor_org_id is not None
    actor = _actor(mongo_test_settings, owner_membership_id)

    evaluation_id, proposal_id, _functional_id, _technical_id = _create_evaluating_proposal(
        mongo_test_settings, tenant_id, vendor_org_id, owner_membership_id
    )
    service = build_ai_service(mongo_test_settings, FakeAIProvider())
    with pytest.raises(RequirementNotInSnapshotError):
        service.request_score_suggestion(
            tenant_id, evaluation_id, proposal_id, ["not-a-real-id"], actor=actor
        )


def test_explicit_request_for_a_section_assigned_to_someone_else_is_rejected(
    mongo_test_settings, seeded_actors
) -> None:
    tenant_id, evaluator_membership_id = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_membership_id = seeded_actors[(tenant_id, "evaluation_owner")]
    _tenant, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    vendor_org_id = _actor(mongo_test_settings, vendor_membership_id).vendor_org_id
    assert vendor_org_id is not None
    actor = _actor(mongo_test_settings, evaluator_membership_id)

    evaluation_id, proposal_id, functional_id, _technical_id = _create_evaluating_proposal(
        mongo_test_settings, tenant_id, vendor_org_id, owner_membership_id
    )
    assignments = AssignmentRepository(_db(mongo_test_settings))
    assignment = Assignment.create(
        tenant_id,
        evaluation_id,
        "functional",
        "Core",
        "someone-else-membership",
        owner_membership_id,
    )
    assignments.insert(tenant_id, assignment.to_document())

    service = build_ai_service(mongo_test_settings, FakeAIProvider())
    with pytest.raises(SectionNotAssignedToActorError):
        service.request_score_suggestion(
            tenant_id, evaluation_id, proposal_id, [functional_id], actor=actor
        )


def test_empty_requirement_ids_silently_excludes_sections_assigned_to_someone_else(
    mongo_test_settings, seeded_actors
) -> None:
    tenant_id, evaluator_membership_id = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_membership_id = seeded_actors[(tenant_id, "evaluation_owner")]
    _tenant, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    vendor_org_id = _actor(mongo_test_settings, vendor_membership_id).vendor_org_id
    assert vendor_org_id is not None
    actor = _actor(mongo_test_settings, evaluator_membership_id)

    evaluation_id, proposal_id, functional_id, technical_id = _create_evaluating_proposal(
        mongo_test_settings, tenant_id, vendor_org_id, owner_membership_id
    )
    assignments = AssignmentRepository(_db(mongo_test_settings))
    assignment = Assignment.create(
        tenant_id,
        evaluation_id,
        "functional",
        "Core",
        "someone-else-membership",
        owner_membership_id,
    )
    assignments.insert(tenant_id, assignment.to_document())

    fake_provider = FakeAIProvider(responses=[_valid_score_response([technical_id])])
    service = build_ai_service(mongo_test_settings, fake_provider)
    execution = service.request_score_suggestion(
        tenant_id, evaluation_id, proposal_id, [], actor=actor
    )
    service.process_score_suggestion_job(tenant_id, execution.id, requirement_ids=[technical_id])

    result = service.get_score_suggestion_execution(
        tenant_id, evaluation_id, proposal_id, execution.id
    )
    assert result.status == "succeeded"
    assert result.candidates is not None
    assert {c["requirement_id"] for c in result.candidates} == {technical_id}
    assert functional_id not in {c["requirement_id"] for c in result.candidates}
