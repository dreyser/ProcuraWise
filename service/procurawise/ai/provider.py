import logging
from typing import Protocol

from procurawise.ai.models import AIRequest, AIResponse
from procurawise.shared.config import Settings

logger = logging.getLogger("procurawise.ai.provider")


class AIProvider(Protocol):
    """Vendor-neutral boundary for LLM calls (ADR 0021). Business services
    (`ai.service`) depend on this Protocol only, never on a concrete
    provider - swapping Azure OpenAI for a second vendor means writing one
    new class against this interface, not touching `ai.service` or any
    domain module. Same shape as `shared.storage.BlobStorage`."""

    def generate(self, request: AIRequest) -> AIResponse: ...

    def ping(self) -> bool: ...


class UnconfiguredAIProvider:
    """Stand-in for when Azure OpenAI isn't configured (local dev's default -
    `Settings` only requires it in production). `request_generation`/
    `get_execution`/`accept_candidates` never call `.generate()` at all, so
    the API and worker must both still start and serve those without a
    provider configured; only an actual generation call fails, cleanly,
    through the normal try/except-and-mark-failed path in
    `AIService.process_generation_job` rather than crashing at startup."""

    def generate(self, request: AIRequest) -> AIResponse:
        raise RuntimeError(
            "Azure OpenAI is not configured (azure_openai_endpoint/api_key/deployment) - "
            "cannot process ai-requirement-generation jobs"
        )

    def ping(self) -> bool:
        return False


def resolve_ai_provider(settings: Settings) -> AIProvider:
    """Single point both `ai.router.get_ai_provider` and `worker/main.py`
    call - avoids each hand-rolling its own try/except around
    AzureOpenAIProvider.from_settings()."""
    # Imported here, not at module level: azure_openai_provider imports the
    # `openai` SDK, and this module (ai.provider) is the Protocol every
    # provider - including future non-Azure ones - is defined against, so it
    # must not itself depend on any one concrete implementation.
    from procurawise.ai.azure_openai_provider import AzureOpenAIProvider

    try:
        return AzureOpenAIProvider.from_settings(settings)
    except ValueError:
        logger.warning(
            "azure_openai_not_configured - ai-requirement-generation jobs will fail until "
            "azure_openai_endpoint/api_key/deployment are set"
        )
        return UnconfiguredAIProvider()
