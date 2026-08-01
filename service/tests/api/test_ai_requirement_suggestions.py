import json

import pytest

from procurawise.ai.models import AIResponse, TokenUsage
from procurawise.ai.router import get_ai_provider
from procurawise.ai.service import build_ai_service
from procurawise.api.main import app
from tests.conftest import bearer_headers_for, unique_actor_by_role
from tests.fakes.fake_ai_provider import FakeAIProvider

pytestmark = pytest.mark.docker


def _valid_candidate(dimension: str = "functional") -> dict:
    return {
        "dimension": dimension,
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


def _valid_response(dimension: str = "functional") -> AIResponse:
    payload = {"candidates": [_valid_candidate(dimension)]}
    return AIResponse(
        raw_output=json.dumps(payload),
        parsed_output=payload,
        token_usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        model="gpt-4o-mini",
        latency_ms=500,
        finish_reason="stop",
    )


def _owner_headers(seeded_actors, mongo_test_settings):
    tenant_a, _ = unique_actor_by_role(seeded_actors, "evaluator_functional")
    return tenant_a, bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )


def _create_evaluation(client, owner_headers) -> str:
    created = client.post(
        "/api/v1/evaluations",
        json={"name": "RFP", "description": ""},
        headers=owner_headers,
    )
    assert created.status_code == 201
    return created.json()["id"]


def _process_job(mongo_test_settings, fake_provider, tenant_id, job_id, *, dimension="functional"):
    ai_service = build_ai_service(mongo_test_settings, fake_provider)
    ai_service.process_generation_job(
        tenant_id, job_id, dimension=dimension, description="We need a reporting tool"
    )


@pytest.fixture(autouse=True)
def _fake_ai_provider():
    fake = FakeAIProvider()
    app.dependency_overrides[get_ai_provider] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_ai_provider, None)


def test_trigger_returns_202_with_job_id_and_status_url(
    client, seeded_actors, mongo_test_settings
) -> None:
    _tenant, owner_headers = _owner_headers(seeded_actors, mongo_test_settings)
    evaluation_id = _create_evaluation(client, owner_headers)

    response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/ai/requirement-suggestions",
        json={"dimension": "functional", "description": "We need a reporting tool"},
        headers=owner_headers,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"]
    assert body["status_url"].endswith(f"/ai/requirement-suggestions/{body['job_id']}")


def test_status_transitions_from_queued_to_succeeded_after_worker_processes(
    client, seeded_actors, mongo_test_settings, _fake_ai_provider
) -> None:
    tenant_a, owner_headers = _owner_headers(seeded_actors, mongo_test_settings)
    evaluation_id = _create_evaluation(client, owner_headers)
    triggered = client.post(
        f"/api/v1/evaluations/{evaluation_id}/ai/requirement-suggestions",
        json={"dimension": "functional", "description": "We need a reporting tool"},
        headers=owner_headers,
    )
    job_id = triggered.json()["job_id"]

    queued = client.get(
        f"/api/v1/evaluations/{evaluation_id}/ai/requirement-suggestions/{job_id}",
        headers=owner_headers,
    )
    assert queued.json()["status"] == "queued"

    _fake_ai_provider.responses = [_valid_response()]
    _process_job(mongo_test_settings, _fake_ai_provider, tenant_a, job_id)

    succeeded = client.get(
        f"/api/v1/evaluations/{evaluation_id}/ai/requirement-suggestions/{job_id}",
        headers=owner_headers,
    )
    body = succeeded.json()
    assert body["status"] == "succeeded"
    assert len(body["candidates"]) == 1
    assert body["candidates"][0]["title"] == "Custom dashboards"
    assert body["model"] == "gpt-4o-mini"
    assert body["token_usage"]["total_tokens"] == 150


def test_accept_adds_requirement_to_evaluation(
    client, seeded_actors, mongo_test_settings, _fake_ai_provider
) -> None:
    tenant_a, owner_headers = _owner_headers(seeded_actors, mongo_test_settings)
    evaluation_id = _create_evaluation(client, owner_headers)
    triggered = client.post(
        f"/api/v1/evaluations/{evaluation_id}/ai/requirement-suggestions",
        json={"dimension": "functional", "description": "We need a reporting tool"},
        headers=owner_headers,
    )
    job_id = triggered.json()["job_id"]
    _fake_ai_provider.responses = [_valid_response()]
    _process_job(mongo_test_settings, _fake_ai_provider, tenant_a, job_id)

    accepted = client.post(
        f"/api/v1/evaluations/{evaluation_id}/ai/requirement-suggestions/{job_id}/accept",
        json={"candidate_indices": [0]},
        headers=owner_headers,
    )
    assert accepted.status_code == 201
    added = accepted.json()["added_requirements"]
    assert len(added) == 1
    assert added[0]["title"] == "Custom dashboards"

    evaluation = client.get(f"/api/v1/evaluations/{evaluation_id}", headers=owner_headers)
    titles = [r["title"] for r in evaluation.json()["requirements"]]
    assert "Custom dashboards" in titles


def test_accept_before_succeeded_is_409(client, seeded_actors, mongo_test_settings) -> None:
    _tenant, owner_headers = _owner_headers(seeded_actors, mongo_test_settings)
    evaluation_id = _create_evaluation(client, owner_headers)
    triggered = client.post(
        f"/api/v1/evaluations/{evaluation_id}/ai/requirement-suggestions",
        json={"dimension": "functional", "description": "We need a reporting tool"},
        headers=owner_headers,
    )
    job_id = triggered.json()["job_id"]

    accepted = client.post(
        f"/api/v1/evaluations/{evaluation_id}/ai/requirement-suggestions/{job_id}/accept",
        json={"candidate_indices": [0]},
        headers=owner_headers,
    )
    assert accepted.status_code == 409


def test_accept_with_out_of_range_index_is_422(
    client, seeded_actors, mongo_test_settings, _fake_ai_provider
) -> None:
    tenant_a, owner_headers = _owner_headers(seeded_actors, mongo_test_settings)
    evaluation_id = _create_evaluation(client, owner_headers)
    triggered = client.post(
        f"/api/v1/evaluations/{evaluation_id}/ai/requirement-suggestions",
        json={"dimension": "functional", "description": "We need a reporting tool"},
        headers=owner_headers,
    )
    job_id = triggered.json()["job_id"]
    _fake_ai_provider.responses = [_valid_response()]
    _process_job(mongo_test_settings, _fake_ai_provider, tenant_a, job_id)

    accepted = client.post(
        f"/api/v1/evaluations/{evaluation_id}/ai/requirement-suggestions/{job_id}/accept",
        json={"candidate_indices": [99]},
        headers=owner_headers,
    )
    assert accepted.status_code == 422


def test_non_owner_cannot_trigger(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, owner_headers = _owner_headers(seeded_actors, mongo_test_settings)
    evaluation_id = _create_evaluation(client, owner_headers)
    evaluator_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluator_functional")], mongo_test_settings
    )

    response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/ai/requirement-suggestions",
        json={"dimension": "functional", "description": "We need a reporting tool"},
        headers=evaluator_headers,
    )
    assert response.status_code == 403


def test_unknown_job_id_is_404(client, seeded_actors, mongo_test_settings) -> None:
    _tenant, owner_headers = _owner_headers(seeded_actors, mongo_test_settings)
    evaluation_id = _create_evaluation(client, owner_headers)

    response = client.get(
        f"/api/v1/evaluations/{evaluation_id}/ai/requirement-suggestions/does-not-exist",
        headers=owner_headers,
    )
    assert response.status_code == 404
