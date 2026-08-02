import json

import pytest

from procurawise.ai.models import AIResponse, TokenUsage
from procurawise.ai.service import build_ai_service
from procurawise.ai.worker import run_worker_loop
from procurawise.evaluations.models import Evaluation
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.shared.config import Settings
from procurawise.shared.context import ActorContext
from procurawise.shared.mongo import get_database
from tests.conftest import TEST_MONGO_DB_NAME, tenant_ids
from tests.fakes.fake_ai_provider import FakeAIProvider

# Needs both Mongo (docker) and the real Service Bus emulator
# (docker_servicebus) - `make test-integration-ai` provisions both, since
# `docker compose --profile servicebus up` starts the default (no-profile)
# services too.
pytestmark = pytest.mark.docker_servicebus

_EMULATOR_CONNECTION_STRING = (
    "Endpoint=sb://localhost;SharedAccessKeyName=RootManageSharedAccessKey;"
    "SharedAccessKey=SAS_KEY_VALUE;UseDevelopmentEmulator=true;"
)


@pytest.fixture
def service_bus_settings() -> Settings:
    return Settings(
        _env_file=None,
        mongodb_db_name=TEST_MONGO_DB_NAME,
        queue_backend="service_bus",
        service_bus_connection_string=_EMULATOR_CONNECTION_STRING,
    )


@pytest.fixture(autouse=True)
def _clean_collections(service_bus_settings):
    db = get_database(service_bus_settings)
    yield
    db["ai_executions"].delete_many({})
    db["evaluations"].delete_many({})


def test_worker_loop_consumes_real_service_bus_message_and_completes_job(
    seeded_actors, service_bus_settings
) -> None:
    tenant_id, _other = tenant_ids(seeded_actors)
    actor = ActorContext(
        membership_id=seeded_actors[(tenant_id, "evaluation_owner")],
        user_id="unused",
        tenant_id=tenant_id,
        tenant_name="tenant",
        role="evaluation_owner",
        vendor_org_id=None,
        display_name="Owner",
    )
    db = get_database(service_bus_settings)
    evaluations = EvaluationRepository(db)
    evaluation = Evaluation.create(tenant_id, "RFP", "", actor.membership_id)
    evaluations.insert(tenant_id, evaluation.to_document())

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
    fake_provider = FakeAIProvider(
        responses=[
            AIResponse(
                raw_output=json.dumps(payload),
                parsed_output=payload,
                token_usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                model="gpt-4o-mini",
                latency_ms=500,
                finish_reason="stop",
            )
        ]
    )
    # request_generation runs with the real ServiceBusMessageBus (via
    # queue_backend=service_bus) - this is the actual cross-process-capable
    # publish, not a direct in-process call.
    trigger_service = build_ai_service(service_bus_settings, fake_provider)
    execution = trigger_service.request_generation(
        tenant_id,
        evaluation.id,
        dimension="functional",
        description="We need a reporting tool",
        actor=actor,
    )
    assert trigger_service.get_execution(tenant_id, evaluation.id, execution.id).status == "queued"

    # A second, independently-constructed AIService/MessageBus - simulating
    # the separate worker process that would consume this in production,
    # not the same in-process object that published it.
    from procurawise.shared.messaging import get_message_bus

    worker_bus = get_message_bus(service_bus_settings)
    worker_service = build_ai_service(service_bus_settings, fake_provider)
    run_worker_loop(worker_bus, worker_service, poll_interval_seconds=0, max_iterations=2)

    result = trigger_service.get_execution(tenant_id, evaluation.id, execution.id)
    assert result.status == "succeeded"
    assert result.candidates is not None
    assert result.candidates[0]["title"] == "Custom dashboards"
