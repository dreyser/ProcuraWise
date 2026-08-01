from collections.abc import Callable
from dataclasses import dataclass, field

from procurawise.ai.models import AIRequest, AIResponse


@dataclass
class FakeAIProvider:
    """Test double for ai.provider.AIProvider - returns a canned AIResponse
    instead of calling Azure OpenAI, so tests exercise the full trigger ->
    generate -> validate -> persist flow with zero network calls and zero
    real API credentials (ADR 0021). Overridden per-test via
    `app.dependency_overrides[get_ai_provider]`, same pattern as
    FakeOidcProvider. `response_factory` (rather than a single fixed
    response) lets a test simulate different outputs per call - e.g. a
    malformed-JSON response on the first call and a valid one on retry."""

    responses: list[AIResponse] = field(default_factory=list)
    response_factory: Callable[[AIRequest], AIResponse] | None = None
    calls: list[AIRequest] = field(default_factory=list)
    raise_on_generate: Exception | None = None

    def generate(self, request: AIRequest) -> AIResponse:
        self.calls.append(request)
        if self.raise_on_generate is not None:
            raise self.raise_on_generate
        if self.response_factory is not None:
            return self.response_factory(request)
        return self.responses[len(self.calls) - 1]

    def ping(self) -> bool:
        return True
