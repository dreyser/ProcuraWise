import json
import queue
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from azure.servicebus import ServiceBusClient, ServiceBusMessage

if TYPE_CHECKING:
    from procurawise.shared.config import Settings


@dataclass(frozen=True)
class Message:
    topic: str
    payload: dict[str, Any]


class MessageBus(Protocol):
    def publish(self, topic: str, payload: dict[str, Any]) -> None: ...

    def consume(self, topic: str) -> Message | None: ...


class InMemoryMessageBus:
    """In-process job queue for local development and unit tests.

    Lives entirely in the memory of a single process: the API and worker are
    started as separate processes by `make dev`, so publishing here does NOT
    make a message visible to the other process. It is not a substitute for a
    real cross-process backend - swap in an Azure Service Bus adapter behind
    the same `MessageBus` protocol once a real async job exists (Fase 13+).
    Never valid in production - see `Settings._reject_memory_queue_in_production`.
    """

    def __init__(self) -> None:
        self._queues: dict[str, queue.Queue[Message]] = {}

    def _queue_for(self, topic: str) -> "queue.Queue[Message]":
        return self._queues.setdefault(topic, queue.Queue())

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        self._queue_for(topic).put_nowait(Message(topic=topic, payload=payload))

    def consume(self, topic: str) -> Message | None:
        try:
            return self._queue_for(topic).get_nowait()
        except queue.Empty:
            return None


class ServiceBusMessageBus:
    """First real cross-process `MessageBus` implementation (Fase 13, ADR
    0005/0020/0021) - `topic` maps to an Azure Service Bus queue name (the
    emulator/queues used today are simple work queues, not pub/sub fan-out,
    so Queues are the right entity, not Topics+Subscriptions despite the
    Protocol's parameter name). A new sender/receiver is opened per call
    rather than held open - simplest correct thing at the MVP's expected
    request volume (NFR-003, <=50 concurrent users); revisit only if
    profiling shows connection overhead actually matters."""

    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string

    @classmethod
    def from_settings(cls, settings: "Settings") -> "ServiceBusMessageBus":
        if not settings.service_bus_connection_string:
            raise ValueError(
                "service_bus_connection_string must be configured to construct ServiceBusMessageBus"
            )
        return cls(settings.service_bus_connection_string)

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        with ServiceBusClient.from_connection_string(self._connection_string) as client:
            with client.get_queue_sender(queue_name=topic) as sender:
                sender.send_messages(ServiceBusMessage(json.dumps(payload)))

    def consume(self, topic: str) -> Message | None:
        with ServiceBusClient.from_connection_string(self._connection_string) as client:
            with client.get_queue_receiver(queue_name=topic, max_wait_time=1) as receiver:
                messages = receiver.receive_messages(max_message_count=1, max_wait_time=1)
                if not messages:
                    return None
                message = messages[0]
                payload = json.loads(str(message))
                receiver.complete_message(message)
                return Message(topic=topic, payload=payload)


def get_message_bus(settings: "Settings") -> MessageBus:
    """Single selection point (ADR 0020/0021): `queue_backend` decides which
    `MessageBus` implementation the API/worker use - callers never
    instantiate `InMemoryMessageBus`/`ServiceBusMessageBus` directly."""
    if settings.queue_backend == "service_bus":
        return ServiceBusMessageBus.from_settings(settings)
    return InMemoryMessageBus()
