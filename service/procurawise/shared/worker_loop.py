import logging
import time
from collections.abc import Callable
from typing import Any

from procurawise.shared.messaging import MessageBus

logger = logging.getLogger("procurawise.worker_loop")

DEFAULT_POLL_INTERVAL_SECONDS = 2.0


def run_worker_loop(
    message_bus: MessageBus,
    dispatch: dict[str, Callable[[dict[str, Any]], None]],
    *,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    max_iterations: int | None = None,
) -> None:
    """Fase 23: generic version of ai.worker.run_worker_loop's body (kept
    byte-for-byte behaviorally identical, extracted so worker/main.py can
    drive a dispatch table merged from more than one module - ai.worker.
    run_worker_loop itself is left untouched, still fully valid and tested,
    just no longer the production entrypoint once a second job family
    (reports) exists. Each iteration checks every registered topic once -
    only sleeps if none of them yielded a message, so a burst of jobs on one
    topic never starves another."""
    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        processed_any = False
        for topic, handler in dispatch.items():
            message = message_bus.consume(topic)
            if message is None:
                continue
            processed_any = True
            try:
                handler(message.payload)
            except Exception:  # noqa: BLE001 - one bad message must never kill the worker loop
                logger.error(
                    "worker_message_processing_failed", exc_info=True, extra={"topic": topic}
                )
        if not processed_any:
            time.sleep(poll_interval_seconds)
        iterations += 1
