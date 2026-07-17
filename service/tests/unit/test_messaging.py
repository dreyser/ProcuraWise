from procurawise.shared.messaging import InMemoryMessageBus


def test_publish_then_consume_returns_message() -> None:
    bus = InMemoryMessageBus()
    bus.publish("reports", {"job_id": "abc123"})

    message = bus.consume("reports")

    assert message is not None
    assert message.topic == "reports"
    assert message.payload == {"job_id": "abc123"}


def test_consume_empty_topic_returns_none() -> None:
    bus = InMemoryMessageBus()
    assert bus.consume("nonexistent") is None


def test_topics_are_isolated_from_each_other() -> None:
    bus = InMemoryMessageBus()
    bus.publish("reports", {"job_id": "1"})

    assert bus.consume("imports") is None
    assert bus.consume("reports") is not None


def test_consume_is_fifo_and_drains() -> None:
    bus = InMemoryMessageBus()
    bus.publish("reports", {"job_id": "1"})
    bus.publish("reports", {"job_id": "2"})

    first = bus.consume("reports")
    second = bus.consume("reports")
    third = bus.consume("reports")

    assert first is not None and first.payload == {"job_id": "1"}
    assert second is not None and second.payload == {"job_id": "2"}
    assert third is None
