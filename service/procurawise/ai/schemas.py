from procurawise.ai.models import AIExecutionStatus
from procurawise.evaluations.models import Dimension, Priority, ResponseType
from procurawise.evaluations.schemas import RequirementResponse
from procurawise.shared.api_models import APIModel


class AIRequirementCandidate(APIModel):
    """The AI-facing candidate shape (ADR 0021 §12): every field required,
    non-nullable - Azure OpenAI's structured-output "strict" mode rejects
    optional/nullable properties, so `buyer_guidance`/`options` use empty
    string/list as "not applicable" rather than None. `ai.service` converts
    an accepted candidate into a real `evaluations.models.Requirement`
    (where those fields ARE optional) at accept time, never before."""

    dimension: Dimension
    category: str
    title: str
    description: str
    priority: Priority
    response_type: ResponseType
    weight: float
    required: bool
    buyer_guidance: str
    options: list[str]
    rationale: str


class AIRequirementCandidateBatch(APIModel):
    candidates: list[AIRequirementCandidate]


class TokenUsageResponse(APIModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class TriggerSuggestionRequest(APIModel):
    dimension: Dimension
    description: str


class TriggerSuggestionResponse(APIModel):
    job_id: str
    status_url: str


class SuggestionJobStatusResponse(APIModel):
    """Shape follows ADR 0012's job status contract:
    queued|running|succeeded|failed. `candidates` is only populated once
    `status == "succeeded"` - never written to Evaluation.requirements
    until POST .../accept is called (ADR 0021 founder decision)."""

    job_id: str
    status: AIExecutionStatus
    candidates: list[AIRequirementCandidate] | None
    error: str | None
    model: str | None
    prompt_version: str
    token_usage: TokenUsageResponse | None
    cost_estimate: float | None
    latency_ms: int | None
    accepted_requirement_ids: list[str]


class AcceptSuggestionsRequest(APIModel):
    candidate_indices: list[int]


class AcceptSuggestionsResponse(APIModel):
    added_requirements: list[RequirementResponse]
