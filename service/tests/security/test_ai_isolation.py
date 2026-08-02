import json

import pytest

from procurawise.ai.models import AIResponse, TokenUsage
from procurawise.ai.router import get_ai_provider
from procurawise.ai.service import build_ai_service
from procurawise.api.main import app
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
