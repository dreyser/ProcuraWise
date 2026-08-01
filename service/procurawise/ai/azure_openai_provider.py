import json
import logging
import time
from datetime import UTC, datetime

from openai import (
    APIConnectionError,
    APITimeoutError,
    AzureOpenAI,
    InternalServerError,
    RateLimitError,
)

from procurawise.ai.models import AIRequest, AIResponse, TokenUsage
from procurawise.shared.config import Settings

logger = logging.getLogger("procurawise.ai.azure_openai")

# Bounded, not open-ended - matches storage.py's discipline of never letting
# an SDK's own default retry policy turn a transient failure into a
# multi-minute wait. Two attempts total (one retry) is enough to smooth over
# a single rate-limit blip without holding the worker hostage.
_MAX_ATTEMPTS = 2
_RETRYABLE_EXCEPTIONS = (RateLimitError, InternalServerError, APIConnectionError, APITimeoutError)


class AzureOpenAIProvider:
    """First (and, for Fase 13, only) implementation of `ai.provider.AIProvider`
    (ADR 0021). Wraps the official `openai` SDK's Azure client - no
    Azure-specific concept leaks past this module into `ai.service` or any
    domain code, which depends on the `AIProvider` Protocol only."""

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        deployment: str,
        api_version: str,
        timeout_seconds: int,
    ) -> None:
        self._deployment = deployment
        self._timeout_seconds = timeout_seconds
        self._client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
            timeout=timeout_seconds,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "AzureOpenAIProvider":
        if not (
            settings.azure_openai_endpoint
            and settings.azure_openai_api_key
            and settings.azure_openai_deployment
        ):
            raise ValueError(
                "azure_openai_endpoint/azure_openai_api_key/azure_openai_deployment must be "
                "configured to construct AzureOpenAIProvider"
            )
        return cls(
            endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            deployment=settings.azure_openai_deployment,
            api_version=settings.azure_openai_api_version,
            timeout_seconds=settings.ai_request_timeout_seconds,
        )

    def generate(self, request: AIRequest) -> AIResponse:
        start = datetime.now(UTC)
        last_error: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self._deployment,
                    messages=[
                        {"role": "system", "content": request.system_prompt},
                        {"role": "user", "content": request.user_prompt},
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "ai_response",
                            "schema": request.response_schema,
                            "strict": True,
                        },
                    },
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                    timeout=request.timeout_seconds,
                )
                break
            except _RETRYABLE_EXCEPTIONS as exc:
                last_error = exc
                logger.warning(
                    "azure_openai_call_retrying",
                    extra={"attempt": attempt, "error_type": type(exc).__name__},
                )
                if attempt < _MAX_ATTEMPTS:
                    time.sleep(2**attempt)
        else:
            assert last_error is not None
            raise last_error

        latency_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
        choice = response.choices[0]
        raw_output = choice.message.content or "{}"
        usage = response.usage
        return AIResponse(
            raw_output=raw_output,
            parsed_output=json.loads(raw_output),
            token_usage=TokenUsage(
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
            ),
            model=response.model,
            latency_ms=latency_ms,
            finish_reason=choice.finish_reason or "unknown",
        )

    def ping(self) -> bool:
        # `with_options(max_retries=0)` overrides the SDK's own default retry
        # policy for this one call only - same rationale as
        # AzureBlobStorage.ping()'s `retry_total=0`: a health check must fail
        # fast, not hang behind the SDK's own backoff.
        self._client.with_options(max_retries=0, timeout=self._timeout_seconds).models.list()
        return True
