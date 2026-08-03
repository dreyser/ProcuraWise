import logging
import time
from collections.abc import Callable
from typing import Any

from procurawise.ai.service import JOB_TOPIC, SCORE_SUGGESTION_JOB_TOPIC, AIService
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


def process_score_suggestion_message(payload: dict[str, Any], *, ai_service: AIService) -> None:
    """Fase 18 (ADR 0022): the second job type this worker dispatches -
    same "call ai.service directly" shape as process_message above."""
    ai_service.process_score_suggestion_job(
        tenant_id=payload["tenant_id"],
        execution_id=payload["execution_id"],
        requirement_ids=payload["requirement_ids"],
    )


def build_dispatch_table(
    ai_service: AIService,
) -> dict[str, Callable[[dict[str, Any]], None]]:
    """Fase 18: `worker/main.py`'s docstring already called itself "the first
    real dispatch table" back in Fase 13, but the loop only ever consumed one
    hardcoded topic - this is the first time more than one topic exists, so
    it's the first time an actual `{topic: handler}` mapping is needed."""
    return {
        JOB_TOPIC: lambda payload: process_message(payload, ai_service=ai_service),
        SCORE_SUGGESTION_JOB_TOPIC: lambda payload: process_score_suggestion_message(
            payload, ai_service=ai_service
        ),
    }


def run_worker_loop(
    message_bus: MessageBus,
    ai_service: AIService,
    *,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    max_iterations: int | None = None,
) -> None:
    """`max_iterations` lets tests run a bounded number of poll cycles
    instead of forever - `worker/main.py` calls this with `max_iterations
    = None` (loops until the process is killed). Each iteration checks every
    registered topic once - only sleeps if none of them yielded a message, so
    a burst of jobs on one topic never starves another (Fase 18)."""
    dispatch = build_dispatch_table(ai_service)
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
                    "ai_worker_message_processing_failed", exc_info=True, extra={"topic": topic}
                )
        if not processed_any:
            time.sleep(poll_interval_seconds)
        iterations += 1
