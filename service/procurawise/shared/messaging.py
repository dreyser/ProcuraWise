import queue
from dataclasses import dataclass
from typing import Any, Protocol


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
