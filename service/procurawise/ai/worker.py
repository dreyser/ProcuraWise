import logging
import time
from typing import Any

from procurawise.ai.service import JOB_TOPIC, AIService
from procurawise.shared.messaging import MessageBus

logger = logging.getLogger("procurawise.ai.worker")

DEFAULT_POLL_INTERVAL_SECONDS = 2.0


def process_message(payload: dict[str, Any], *, ai_service: AIService) -> None:
    """Fase 13's first real worker job (ADR 0001/0005): calls `ai.service`
    directly, never internal HTTP - same code path `ai.router` would call
    synchronously, run out-of-band instead."""
    ai_service.process_generation_job(
        tenant_id=payload["tenant_id"],
        execution_id=payload["execution_id"],
        dimension=payload["dimension"],
        description=payload["description"],
    )


def run_worker_loop(
    message_bus: MessageBus,
    ai_service: AIService,
    *,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    max_iterations: int | None = None,
) -> None:
    """`max_iterations` lets tests run a bounded number of poll cycles
    instead of forever - `worker/main.py` calls this with `max_iterations
    = None` (loops until the process is killed)."""
    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        message = message_bus.consume(JOB_TOPIC)
        if message is None:
            time.sleep(poll_interval_seconds)
        else:
            try:
                process_message(message.payload, ai_service=ai_service)
            except Exception:  # noqa: BLE001 - one bad message must never kill the worker loop
                logger.error("ai_worker_message_processing_failed", exc_info=True)
        iterations += 1
