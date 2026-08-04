from unittest.mock import MagicMock

from procurawise.ai.service import JOB_TOPIC, SCORE_SUGGESTION_JOB_TOPIC
from procurawise.ai.worker import (
    process_message,
    process_score_suggestion_message,
    run_worker_loop,
)
from procurawise.shared.messaging import InMemoryMessageBus


def test_process_message_calls_service_with_payload_fields() -> None:
    ai_service = MagicMock()
    payload = {
        "tenant_id": "tenant-a",
        "execution_id": "exec-1",
        "dimension": "functional",
        "description": "need a reporting tool",
    }

    process_message(payload, ai_service=ai_service)

    ai_service.process_generation_job.assert_called_once_with(
        tenant_id="tenant-a",
        execution_id="exec-1",
        dimension="functional",
        description="need a reporting tool",
    )


def test_run_worker_loop_processes_queued_message_then_stops_at_max_iterations() -> None:
    bus = InMemoryMessageBus()
    bus.publish(
        JOB_TOPIC,
        {"tenant_id": "t", "execution_id": "e", "dimension": "functional", "description": "d"},
    )
    ai_service = MagicMock()

    run_worker_loop(bus, ai_service, poll_interval_seconds=0, max_iterations=1)

    ai_service.process_generation_job.assert_called_once()


def test_run_worker_loop_survives_a_processing_exception(monkeypatch) -> None:
    bus = InMemoryMessageBus()
    bus.publish(
        JOB_TOPIC,
        {"tenant_id": "t", "execution_id": "e", "dimension": "functional", "description": "d"},
    )
    ai_service = MagicMock()
    ai_service.process_generation_job.side_effect = RuntimeError("boom")

    # Must not raise - a single bad message must never kill the worker loop.
    run_worker_loop(bus, ai_service, poll_interval_seconds=0, max_iterations=1)


def test_run_worker_loop_sleeps_when_queue_empty(monkeypatch) -> None:
    bus = InMemoryMessageBus()
    ai_service = MagicMock()
    sleep_calls = []
    monkeypatch.setattr(
        "procurawise.ai.worker.time.sleep", lambda seconds: sleep_calls.append(seconds)
    )

    run_worker_loop(bus, ai_service, poll_interval_seconds=5, max_iterations=1)

    assert sleep_calls == [5]
    ai_service.process_generation_job.assert_not_called()


def test_process_score_suggestion_message_calls_service_with_payload_fields() -> None:
    ai_service = MagicMock()
    payload = {
        "tenant_id": "tenant-a",
        "execution_id": "exec-1",
        "requirement_ids": ["req-1", "req-2"],
    }

    process_score_suggestion_message(payload, ai_service=ai_service)

    ai_service.process_score_suggestion_job.assert_called_once_with(
        tenant_id="tenant-a",
        execution_id="exec-1",
        requirement_ids=["req-1", "req-2"],
    )


def test_run_worker_loop_dispatches_both_topics_independently() -> None:
    # Fase 18 (ADR 0022): the worker is no longer single-topic - a message on
    # ai-score-suggestion must reach process_score_suggestion_job without
    # ever touching process_generation_job, and vice versa (test_
    # run_worker_loop_processes_queued_message_then_stops_at_max_iterations
    # above already covers the JOB_TOPIC side alone).
    bus = InMemoryMessageBus()
    bus.publish(
        SCORE_SUGGESTION_JOB_TOPIC,
        {"tenant_id": "t", "execution_id": "e", "requirement_ids": ["req-1"]},
    )
    ai_service = MagicMock()

    run_worker_loop(bus, ai_service, poll_interval_seconds=0, max_iterations=1)

    ai_service.process_score_suggestion_job.assert_called_once_with(
        tenant_id="t", execution_id="e", requirement_ids=["req-1"]
    )
    ai_service.process_generation_job.assert_not_called()


def test_run_worker_loop_processes_one_message_per_topic_in_the_same_iteration() -> None:
    bus = InMemoryMessageBus()
    bus.publish(
        JOB_TOPIC,
        {"tenant_id": "t", "execution_id": "e1", "dimension": "functional", "description": "d"},
    )
    bus.publish(
        SCORE_SUGGESTION_JOB_TOPIC,
        {"tenant_id": "t", "execution_id": "e2", "requirement_ids": ["req-1"]},
    )
    ai_service = MagicMock()

    run_worker_loop(bus, ai_service, poll_interval_seconds=0, max_iterations=1)

    ai_service.process_generation_job.assert_called_once()
    ai_service.process_score_suggestion_job.assert_called_once()
