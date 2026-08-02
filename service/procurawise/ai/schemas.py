from datetime import datetime

from procurawise.ai.models import AIExecutionStatus
from procurawise.ai.research_provider import ResearchSourceType, ResearchWarningCode
from procurawise.evaluations.models import Dimension, Priority, ResponseType
from procurawise.evaluations.schemas import RequirementResponse
from procurawise.shared.api_models import APIModel


class AIRequirementCandidate(APIModel):
    """The AI-facing candidate shape (ADR 0021 §12): every field required,
    non-nullable - Azure OpenAI's structured-output "strict" mode rejects
    optional/nullable properties, so `buyer_guidance`/`options`/`sources`
    use empty string/list as "not applicable" rather than None. `ai.service`
    converts an accepted candidate into a real `evaluations.models.
    Requirement` (where those fields ARE optional) at accept time, never
    before.

    Fase 14 (ADR 0011): `sources` holds `ResearchSnippet.source_id` values
    the model was instructed to cite from the job's own `source_catalog` -
    never a `url` directly. `ai.service` validates every id against that
    job's immutable catalog (never the live, mutable curated_sources
    collection) both at generation time and again at accept time, stripping
    any unknown/invented id - a URL shown to a user always comes from the
    persisted catalog, never from raw model output (founder decision, Fase
    14 planning)."""

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
    sources: list[str]


class ResearchSnippetResponse(APIModel):
    """Fase 14: one entry of a job's immutable `source_catalog` snapshot -
    the only place a citation's `url` is ever read from when rendering it to
    a user (never from `AIRequirementCandidate` directly, which only carries
    `source_id` references)."""

    source_type: ResearchSourceType
    source_id: str
    title: str
    url: str | None
    retrieved_at: datetime | None


class ResearchWarningResponse(APIModel):
    code: ResearchWarningCode
    source_type: ResearchSourceType
    message: str


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
    # Fase 14: populated directly from AIExecution.source_catalog/warnings -
    # never a live query, so the frontend resolves candidate.sources (ids)
    # into citations purely from this job-scoped, immutable snapshot.
    source_catalog: list[ResearchSnippetResponse]
    warnings: list[ResearchWarningResponse]


class AcceptSuggestionsRequest(APIModel):
    candidate_indices: list[int]


class AcceptSuggestionsResponse(APIModel):
    added_requirements: list[RequirementResponse]
