from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

AIExecutionStatus = Literal["queued", "running", "succeeded", "failed"]

# Fase 13 (ADR 0021) only implemented requirement generation. Fase 18 (ADR
# 0022) adds "score_suggestion" as the second use case anticipated by this
# Literal's original comment - each has its own prompt directory
# (ai/prompts/<use_case>/) - never a free-form string.
AIUseCase = Literal["requirement_generation", "score_suggestion"]


def new_id() -> str:
    return uuid4().hex


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    def to_document(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "TokenUsage":
        return TokenUsage(
            prompt_tokens=doc["prompt_tokens"],
            completion_tokens=doc["completion_tokens"],
            total_tokens=doc["total_tokens"],
        )


@dataclass(frozen=True)
class AIRequest:
    """Provider call contract - never persisted directly (ADR 0021: the raw
    prompt text is not stored, only prompt_template/prompt_version on
    AIExecution). `response_schema` is a JSON schema dict the provider is
    asked to constrain its output to."""

    system_prompt: str
    user_prompt: str
    response_schema: dict[str, Any]
    max_tokens: int
    timeout_seconds: int


@dataclass(frozen=True)
class AIResponse:
    raw_output: str
    parsed_output: dict[str, Any]
    token_usage: TokenUsage
    model: str
    latency_ms: int
    finish_reason: str


@dataclass(frozen=True)
class AIExecution:
    """The AIProvider analog of AuditEvent (ADR 0021): one record per job,
    tracking cost/model/prompt-version per the Fase 13 acceptance criterion.
    `candidates` is deliberately ephemeral business data, not a source of
    truth - nothing here becomes a real Requirement (requirement_generation)
    or a real Score (score_suggestion, Fase 18/ADR 0022) until a human acts
    explicitly. requirement_generation writes through
    EvaluationRepository.add_requirements_bulk; score_suggestion is never
    written by `ai/` at all - accepting/modifying a suggestion is just a
    normal call to the existing ScoringService.upsert_score, which optionally
    references this execution's id for provenance."""

    id: str
    tenant_id: str
    evaluation_id: str
    # Fase 18 (ADR 0022): populated only for use_case=="score_suggestion" -
    # a requirement_generation job (Fase 13) has no proposal/snapshot of its
    # own, it edits Evaluation.requirements directly. None on every job that
    # predates this field, and on every requirement_generation job going
    # forward too - never backfilled.
    proposal_id: str | None
    snapshot_id: str | None
    requested_by_membership_id: str
    use_case: AIUseCase
    status: AIExecutionStatus
    provider: str
    model: str | None
    prompt_template: str
    prompt_version: str
    token_usage: TokenUsage | None
    cost_estimate: float | None
    latency_ms: int | None
    candidates: list[dict[str, Any]] | None
    accepted_requirement_ids: list[str]
    error: str | None
    # Fase 14 (ADR 0011): the exact ResearchSnippets gathered for this job,
    # written once at generation time and never updated afterward - the
    # source of truth for candidate citations (schemas.AIRequirementCandidate
    # .sources references these ids). Deliberately NOT re-derived from the
    # live curated_sources collection on read, so a later edit/deactivation
    # of a CuratedSource never retroactively changes what an already-
    # generated job cites (founder decision, Fase 14 planning).
    source_catalog: list[dict[str, Any]]
    # Structured, provider-neutral degradation of a *secondary* research
    # source (never InternalKnowledgeProvider, whose failure is still a hard
    # job failure) - distinct from `error`, which stays reserved for jobs
    # that fail outright. Never raw provider exception text.
    warnings: list[dict[str, Any]]
    created_at: datetime
    completed_at: datetime | None
    expires_at: datetime

    @staticmethod
    def create(
        *,
        tenant_id: str,
        evaluation_id: str,
        requested_by_membership_id: str,
        use_case: AIUseCase,
        provider: str,
        prompt_template: str,
        prompt_version: str,
        retention_days: int,
        proposal_id: str | None = None,
        snapshot_id: str | None = None,
    ) -> "AIExecution":
        now = datetime.now(UTC)
        return AIExecution(
            id=new_id(),
            tenant_id=tenant_id,
            evaluation_id=evaluation_id,
            proposal_id=proposal_id,
            snapshot_id=snapshot_id,
            requested_by_membership_id=requested_by_membership_id,
            use_case=use_case,
            status="queued",
            provider=provider,
            model=None,
            prompt_template=prompt_template,
            prompt_version=prompt_version,
            token_usage=None,
            cost_estimate=None,
            latency_ms=None,
            candidates=None,
            accepted_requirement_ids=[],
            error=None,
            source_catalog=[],
            warnings=[],
            created_at=now,
            completed_at=None,
            expires_at=now + timedelta(days=retention_days),
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "tenant_id": self.tenant_id,
            "evaluation_id": self.evaluation_id,
            "proposal_id": self.proposal_id,
            "snapshot_id": self.snapshot_id,
            "requested_by_membership_id": self.requested_by_membership_id,
            "use_case": self.use_case,
            "status": self.status,
            "provider": self.provider,
            "model": self.model,
            "prompt_template": self.prompt_template,
            "prompt_version": self.prompt_version,
            "token_usage": self.token_usage.to_document() if self.token_usage else None,
            "cost_estimate": self.cost_estimate,
            "latency_ms": self.latency_ms,
            "candidates": self.candidates,
            "accepted_requirement_ids": self.accepted_requirement_ids,
            "error": self.error,
            "source_catalog": self.source_catalog,
            "warnings": self.warnings,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "expires_at": self.expires_at,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "AIExecution":
        token_usage_doc = doc.get("token_usage")
        return AIExecution(
            id=doc["_id"],
            tenant_id=doc["tenant_id"],
            evaluation_id=doc["evaluation_id"],
            proposal_id=doc.get("proposal_id"),
            snapshot_id=doc.get("snapshot_id"),
            requested_by_membership_id=doc["requested_by_membership_id"],
            use_case=doc["use_case"],
            status=doc["status"],
            provider=doc["provider"],
            model=doc.get("model"),
            prompt_template=doc["prompt_template"],
            prompt_version=doc["prompt_version"],
            token_usage=TokenUsage.from_document(token_usage_doc) if token_usage_doc else None,
            cost_estimate=doc.get("cost_estimate"),
            latency_ms=doc.get("latency_ms"),
            candidates=doc.get("candidates"),
            accepted_requirement_ids=doc.get("accepted_requirement_ids", []),
            error=doc.get("error"),
            source_catalog=doc.get("source_catalog", []),
            warnings=doc.get("warnings", []),
            created_at=doc["created_at"],
            completed_at=doc.get("completed_at"),
            expires_at=doc["expires_at"],
        )
