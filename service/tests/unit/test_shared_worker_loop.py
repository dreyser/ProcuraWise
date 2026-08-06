from unittest.mock import MagicMock

from procurawise.shared.messaging import InMemoryMessageBus
from procurawise.shared.worker_loop import run_worker_loop


def test_run_worker_loop_dispatches_to_the_matching_topic_handler() -> None:
    bus = InMemoryMessageBus()
    bus.publish("topic-a", {"value": 1})
    handler_a = MagicMock()
    handler_b = MagicMock()

    run_worker_loop(
        bus, {"topic-a": handler_a, "topic-b": handler_b}, poll_interval_seconds=0, max_iterations=1
    )

    handler_a.assert_called_once_with({"value": 1})
    handler_b.assert_not_called()


def test_run_worker_loop_survives_a_handler_exception() -> None:
    bus = InMemoryMessageBus()
    bus.publish("topic-a", {"value": 1})
    handler = MagicMock(side_effect=RuntimeError("boom"))

    # Must not raise.
    run_worker_loop(bus, {"topic-a": handler}, poll_interval_seconds=0, max_iterations=1)


def test_run_worker_loop_sleeps_when_every_topic_is_empty(monkeypatch) -> None:
    bus = InMemoryMessageBus()
    handler = MagicMock()
    sleep_calls = []
    monkeypatch.setattr(
        "procurawise.shared.worker_loop.time.sleep", lambda seconds: sleep_calls.append(seconds)
    )

    run_worker_loop(bus, {"topic-a": handler}, poll_interval_seconds=5, max_iterations=1)

    assert sleep_calls == [5]
    handler.assert_not_called()
