from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

AIExecutionStatus = Literal["queued", "running", "succeeded", "failed"]

# Fase 13 (ADR 0021) only implements requirement generation. A second use
# case (e.g. a future "improve requirement" call) adds its own literal value
# here and its own prompt directory (ai/prompts/) - never a free-form string.
AIUseCase = Literal["requirement_generation"]


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
    temperature: float
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
    truth - nothing here becomes a real Requirement until a human calls the
    accept endpoint (Block 4), which writes through the existing
    EvaluationRepository.add_requirements_bulk atomic path."""

    id: str
    tenant_id: str
    evaluation_id: str
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
    ) -> "AIExecution":
        now = datetime.now(UTC)
        return AIExecution(
            id=new_id(),
            tenant_id=tenant_id,
            evaluation_id=evaluation_id,
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
            created_at=now,
            completed_at=None,
            expires_at=now + timedelta(days=retention_days),
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "tenant_id": self.tenant_id,
            "evaluation_id": self.evaluation_id,
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
            created_at=doc["created_at"],
            completed_at=doc.get("completed_at"),
            expires_at=doc["expires_at"],
        )
