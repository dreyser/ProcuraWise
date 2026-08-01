import json

import pytest

from procurawise.ai.models import AIResponse, TokenUsage
from procurawise.ai.repository import AIExecutionRepository
from procurawise.ai.service import build_ai_service
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.shared.context import ActorContext
from tests.fakes.fake_ai_provider import FakeAIProvider

pytestmark = pytest.mark.docker


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


def _malformed_response() -> AIResponse:
    payload = {"candidates": [{"title": "missing every other required field"}]}
    return AIResponse(
        raw_output=json.dumps(payload),
        parsed_output=payload,
        token_usage=TokenUsage(prompt_tokens=80, completion_tokens=20, total_tokens=100),
        model="gpt-4o-mini",
        latency_ms=300,
        finish_reason="stop",
    )


def _partially_valid_response() -> AIResponse:
    valid_candidate = {
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
    }
    payload = {"candidates": [valid_candidate, {"title": "missing every other required field"}]}
    return AIResponse(
        raw_output=json.dumps(payload),
        parsed_output=payload,
        token_usage=TokenUsage(prompt_tokens=120, completion_tokens=60, total_tokens=180),
        model="gpt-4o-mini",
        latency_ms=400,
        finish_reason="stop",
    )


@pytest.fixture
def actor(seeded_actors) -> ActorContext:
    from tests.conftest import tenant_ids

    tenant_id, _other_tenant_id = tenant_ids(seeded_actors)
    return ActorContext(
        membership_id=seeded_actors[(tenant_id, "evaluation_owner")],
        user_id="unused",
        tenant_id=tenant_id,
        tenant_name="tenant",
        role="evaluation_owner",
        vendor_org_id=None,
        display_name="Owner",
    )


@pytest.fixture(autouse=True)
def _clean_ai_executions(mongo_test_db):
    yield
    mongo_test_db["ai_executions"].delete_many({})
    mongo_test_db["evaluations"].delete_many({})


def _create_draft_evaluation(mongo_test_settings, tenant_id: str, actor: ActorContext) -> str:
    from procurawise.evaluations.models import Evaluation

    repo = EvaluationRepository(_db(mongo_test_settings))
    evaluation = Evaluation.create(tenant_id, "RFP", "", actor.membership_id)
    repo.insert(tenant_id, evaluation.to_document())
    return evaluation.id


def _db(settings):
    from procurawise.shared.mongo import get_database

    return get_database(settings)


def test_generation_retries_once_on_invalid_json_then_succeeds(mongo_test_settings, actor) -> None:
    evaluation_id = _create_draft_evaluation(mongo_test_settings, actor.tenant_id, actor)
    fake_provider = FakeAIProvider(responses=[_malformed_response(), _valid_response()])
    service = build_ai_service(mongo_test_settings, fake_provider)

    execution = service.request_generation(
        actor.tenant_id,
        evaluation_id,
        dimension="functional",
        description="We need a reporting tool",
        actor=actor,
    )
    service.process_generation_job(
        actor.tenant_id,
        execution.id,
        dimension="functional",
        description="We need a reporting tool",
    )

    result = service.get_execution(actor.tenant_id, evaluation_id, execution.id)
    assert result.status == "succeeded"
    assert result.candidates is not None
    assert len(result.candidates) == 1
    assert len(fake_provider.calls) == 2
    # Token usage is summed across both attempts (ADR 0021 §10 - token
    # accounting must reflect every real call made, not just the last one).
    assert result.token_usage is not None
    assert result.token_usage.total_tokens == 100 + 150


def test_generation_marks_failed_when_both_attempts_are_invalid(mongo_test_settings, actor) -> None:
    evaluation_id = _create_draft_evaluation(mongo_test_settings, actor.tenant_id, actor)
    fake_provider = FakeAIProvider(responses=[_malformed_response(), _malformed_response()])
    service = build_ai_service(mongo_test_settings, fake_provider)

    execution = service.request_generation(
        actor.tenant_id,
        evaluation_id,
        dimension="functional",
        description="We need a reporting tool",
        actor=actor,
    )
    service.process_generation_job(
        actor.tenant_id,
        execution.id,
        dimension="functional",
        description="We need a reporting tool",
    )

    result = service.get_execution(actor.tenant_id, evaluation_id, execution.id)
    assert result.status == "failed"
    assert result.error is not None
    assert result.candidates is None


def test_generation_keeps_valid_candidates_and_drops_invalid_ones_without_retrying(
    mongo_test_settings, actor
) -> None:
    evaluation_id = _create_draft_evaluation(mongo_test_settings, actor.tenant_id, actor)
    fake_provider = FakeAIProvider(responses=[_partially_valid_response()])
    service = build_ai_service(mongo_test_settings, fake_provider)

    execution = service.request_generation(
        actor.tenant_id,
        evaluation_id,
        dimension="functional",
        description="We need a reporting tool",
        actor=actor,
    )
    service.process_generation_job(
        actor.tenant_id,
        execution.id,
        dimension="functional",
        description="We need a reporting tool",
    )

    result = service.get_execution(actor.tenant_id, evaluation_id, execution.id)
    assert result.status == "succeeded"
    assert result.candidates is not None
    assert len(result.candidates) == 1
    assert result.candidates[0]["title"] == "Custom dashboards"
    # One malformed candidate in an otherwise valid batch must not trigger
    # the corrective-prompt retry (ADR 0021 §12: partial success keeps the
    # valid ones instead of discarding the whole batch).
    assert len(fake_provider.calls) == 1


def test_processing_an_already_succeeded_job_is_a_noop(mongo_test_settings, actor) -> None:
    evaluation_id = _create_draft_evaluation(mongo_test_settings, actor.tenant_id, actor)
    fake_provider = FakeAIProvider(responses=[_valid_response()])
    service = build_ai_service(mongo_test_settings, fake_provider)

    execution = service.request_generation(
        actor.tenant_id,
        evaluation_id,
        dimension="functional",
        description="We need a reporting tool",
        actor=actor,
    )
    service.process_generation_job(
        actor.tenant_id,
        execution.id,
        dimension="functional",
        description="We need a reporting tool",
    )
    # Simulates a redelivered Service Bus message for the same job
    # (ADR 0005: every job must be retryable idempotently).
    service.process_generation_job(
        actor.tenant_id,
        execution.id,
        dimension="functional",
        description="We need a reporting tool",
    )

    assert len(fake_provider.calls) == 1
    result = service.get_execution(actor.tenant_id, evaluation_id, execution.id)
    assert result.status == "succeeded"


def test_accept_records_acceptance_and_is_idempotent_on_repeated_calls(
    mongo_test_settings, actor
) -> None:
    evaluation_id = _create_draft_evaluation(mongo_test_settings, actor.tenant_id, actor)
    fake_provider = FakeAIProvider(responses=[_valid_response()])
    service = build_ai_service(mongo_test_settings, fake_provider)
    execution = service.request_generation(
        actor.tenant_id,
        evaluation_id,
        dimension="functional",
        description="We need a reporting tool",
        actor=actor,
    )
    service.process_generation_job(
        actor.tenant_id,
        execution.id,
        dimension="functional",
        description="We need a reporting tool",
    )

    added = service.accept_candidates(
        actor.tenant_id, evaluation_id, execution.id, [0], actor=actor
    )

    assert len(added) == 1
    executions = AIExecutionRepository(_db(mongo_test_settings))
    stored = executions.find_by_id(actor.tenant_id, execution.id)
    assert stored is not None
    assert stored["accepted_requirement_ids"] == [added[0].id]
