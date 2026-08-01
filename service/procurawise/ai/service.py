import logging
from datetime import UTC, datetime

from pydantic import ValidationError

from procurawise.ai.exceptions import (
    AIExecutionNotFoundError,
    InvalidAIExecutionStateError,
    InvalidCandidateSelectionError,
)
from procurawise.ai.internal_knowledge_provider import InternalKnowledgeProvider
from procurawise.ai.models import AIExecution, AIRequest, TokenUsage
from procurawise.ai.prompt_renderer import render_prompt
from procurawise.ai.provider import AIProvider
from procurawise.ai.repository import AIExecutionRepository
from procurawise.ai.research_provider import DiscoveryQuery, ResearchProvider, ResearchSnippet
from procurawise.ai.schemas import AIRequirementCandidate, AIRequirementCandidateBatch
from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.service import AuditEventService
from procurawise.evaluations.exceptions import EvaluationNotFoundError, InvalidTransitionError
from procurawise.evaluations.models import Dimension, Evaluation, Requirement
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.repository import MembershipRepository, TenantRepository, UserRepository
from procurawise.identity.service import ActorNotFoundError, IdentityService
from procurawise.knowledge_templates.repository import KnowledgeTemplateRepository
from procurawise.shared.config import Settings
from procurawise.shared.context import ActorContext
from procurawise.shared.messaging import MessageBus, get_message_bus
from procurawise.shared.mongo import get_database

logger = logging.getLogger("procurawise.ai")

PROMPT_TEMPLATE = "requirement_generation"
PROMPT_VERSION = "v1"
JOB_TOPIC = "ai-requirement-generation"

_MAX_TOKENS = 2000
_TEMPERATURE = 0.3
_MAX_GENERATION_ATTEMPTS = 2


def _render_context(snippets: list[ResearchSnippet]) -> str:
    if not snippets:
        return "(sin contexto interno disponible)"
    return "\n".join(f"- {snippet.title}: {snippet.content}" for snippet in snippets)


class _NoValidCandidatesError(Exception):
    """Every item in an otherwise well-shaped `candidates` list failed
    per-item validation - treated the same as a malformed response (worth
    the one retry), unlike a partial batch where some candidates are kept."""


def _parse_candidates(parsed_output: dict) -> tuple[list[AIRequirementCandidate], int]:
    """Validates each candidate independently (ADR 0021 §12: partial
    success keeps the valid candidates instead of discarding the whole
    batch for one malformed item). A missing/non-list `candidates` field is
    a structural failure - reuses AIRequirementCandidateBatch's own
    validation to raise a consistent ValidationError for that case, letting
    the caller's retry-with-corrective-prompt path handle it."""
    raw_candidates = parsed_output.get("candidates")
    if not isinstance(raw_candidates, list):
        AIRequirementCandidateBatch.model_validate(parsed_output)
        raise AssertionError("unreachable - model_validate should have raised ValidationError")

    valid: list[AIRequirementCandidate] = []
    invalid_count = 0
    for raw_candidate in raw_candidates:
        try:
            valid.append(AIRequirementCandidate.model_validate(raw_candidate))
        except ValidationError:
            invalid_count += 1

    if not valid and raw_candidates:
        raise _NoValidCandidatesError(f"all {len(raw_candidates)} candidates failed validation")
    return valid, invalid_count


class AIService:
    """Orchestrates discover -> render -> generate -> validate -> persist
    (ADR 0021 §12). Request/status/accept are called by the API router;
    process_generation_job is called by the worker's dispatch loop (never by
    the API directly, per ADR 0001/0005 - the worker calls this same code
    path a synchronous call would use)."""

    def __init__(
        self,
        executions: AIExecutionRepository,
        evaluations: EvaluationRepository,
        research: ResearchProvider,
        provider: AIProvider,
        identity: IdentityService,
        audit: AuditEventService,
        message_bus: MessageBus,
        *,
        retention_days: int,
        request_timeout_seconds: int,
        prompt_price_per_1k: float | None,
        completion_price_per_1k: float | None,
    ) -> None:
        self._executions = executions
        self._evaluations = evaluations
        self._research = research
        self._provider = provider
        self._identity = identity
        self._audit = audit
        self._message_bus = message_bus
        self._retention_days = retention_days
        self._request_timeout_seconds = request_timeout_seconds
        self._prompt_price_per_1k = prompt_price_per_1k
        self._completion_price_per_1k = completion_price_per_1k

    def request_generation(
        self,
        tenant_id: str,
        evaluation_id: str,
        *,
        dimension: Dimension,
        description: str,
        actor: ActorContext,
    ) -> AIExecution:
        evaluation = self._draft_evaluation_or_raise(tenant_id, evaluation_id)

        execution = AIExecution.create(
            tenant_id=tenant_id,
            evaluation_id=evaluation.id,
            requested_by_membership_id=actor.membership_id,
            use_case="requirement_generation",
            provider="azure_openai",
            prompt_template=PROMPT_TEMPLATE,
            prompt_version=PROMPT_VERSION,
            retention_days=self._retention_days,
        )
        self._executions.insert(tenant_id, execution.to_document())
        self._message_bus.publish(
            JOB_TOPIC,
            {
                "tenant_id": tenant_id,
                "execution_id": execution.id,
                "dimension": dimension,
                "description": description,
            },
        )
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="ai_generation_requested",
            resource_type="ai_execution",
            resource_id=execution.id,
            evaluation_id=evaluation.id,
            metadata={"prompt_template": PROMPT_TEMPLATE, "prompt_version": PROMPT_VERSION},
        )
        return execution

    def get_execution(self, tenant_id: str, evaluation_id: str, execution_id: str) -> AIExecution:
        doc = self._executions.find_by_id(tenant_id, execution_id)
        if doc is None:
            raise AIExecutionNotFoundError(execution_id)
        execution = AIExecution.from_document(doc)
        if execution.evaluation_id != evaluation_id:
            raise AIExecutionNotFoundError(execution_id)
        return execution

    def process_generation_job(
        self, tenant_id: str, execution_id: str, *, dimension: Dimension, description: str
    ) -> None:
        doc = self._executions.find_by_id(tenant_id, execution_id)
        if doc is None:
            logger.error("ai_execution_not_found_for_job", extra={"execution_id": execution_id})
            return
        execution = AIExecution.from_document(doc)
        if execution.status != "queued":
            # Idempotency guard (ADR 0005: every job must be retryable
            # idempotently) - a redelivered message for an already-processed
            # execution is a no-op, not an error.
            return
        if not self._executions.transition_status(tenant_id, execution_id, "queued", "running"):
            return

        try:
            candidates, model, token_usage, latency_ms, dropped_count = self._generate_candidates(
                tenant_id, execution, dimension=dimension, description=description
            )
        except Exception as exc:  # noqa: BLE001 - any provider/validation failure lands the job in `failed`, never crashes the worker loop
            logger.error(
                "ai_generation_failed",
                extra={"execution_id": execution_id, "error_type": type(exc).__name__},
                exc_info=True,
            )
            self._executions.transition_status(
                tenant_id,
                execution_id,
                "running",
                "failed",
                extra_set={"error": str(exc), "completed_at": datetime.now(UTC)},
            )
            self._record_failure_audit(tenant_id, execution, str(exc))
            return

        cost_estimate = self._estimate_cost(token_usage)
        self._executions.transition_status(
            tenant_id,
            execution_id,
            "running",
            "succeeded",
            extra_set={
                "model": model,
                "token_usage": token_usage.to_document(),
                "cost_estimate": cost_estimate,
                "latency_ms": latency_ms,
                "candidates": [candidate.model_dump() for candidate in candidates],
                "completed_at": datetime.now(UTC),
            },
        )
        self._record_success_audit(tenant_id, execution, len(candidates), dropped_count)

    def accept_candidates(
        self,
        tenant_id: str,
        evaluation_id: str,
        execution_id: str,
        candidate_indices: list[int],
        *,
        actor: ActorContext,
    ) -> list[Requirement]:
        execution = self.get_execution(tenant_id, evaluation_id, execution_id)
        if execution.status != "succeeded" or execution.candidates is None:
            raise InvalidAIExecutionStateError(execution_id)
        evaluation = self._draft_evaluation_or_raise(tenant_id, evaluation_id)

        next_display_order = len(evaluation.requirements) + 1
        new_requirements: list[Requirement] = []
        for offset, index in enumerate(candidate_indices):
            if index < 0 or index >= len(execution.candidates):
                raise InvalidCandidateSelectionError(f"candidate index {index} out of range")
            candidate = AIRequirementCandidate.model_validate(execution.candidates[index])
            try:
                new_requirements.append(
                    _requirement_from_candidate(candidate, next_display_order + offset)
                )
            except ValueError as exc:
                raise InvalidCandidateSelectionError(
                    f"candidate at index {index} is invalid: {exc}"
                ) from exc

        if new_requirements:
            self._evaluations.add_requirements_bulk(
                tenant_id,
                evaluation_id,
                [requirement.to_document() for requirement in new_requirements],
                evaluation.approval_invalidation_extra_set(),
            )
        accepted_ids = [*execution.accepted_requirement_ids, *[r.id for r in new_requirements]]
        self._executions.record_acceptance(tenant_id, execution_id, accepted_ids)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="ai_requirements_accepted",
            resource_type="ai_execution",
            resource_id=execution_id,
            evaluation_id=evaluation_id,
            metadata={
                "accepted_count": len(new_requirements),
                "requirement_ids": [r.id for r in new_requirements],
            },
        )
        return new_requirements

    def _draft_evaluation_or_raise(self, tenant_id: str, evaluation_id: str) -> Evaluation:
        evaluation_doc = self._evaluations.find_by_id(tenant_id, evaluation_id)
        if evaluation_doc is None:
            raise EvaluationNotFoundError(evaluation_id)
        evaluation = Evaluation.from_document(evaluation_doc)
        if evaluation.status != "draft":
            raise InvalidTransitionError(evaluation_id)
        return evaluation

    def _generate_candidates(
        self, tenant_id: str, execution: AIExecution, *, dimension: Dimension, description: str
    ) -> tuple[list[AIRequirementCandidate], str, TokenUsage, int, int]:
        snippets = self._research.discover(
            tenant_id,
            DiscoveryQuery(
                dimension=dimension,
                description=description,
                exclude_evaluation_id=execution.evaluation_id,
            ),
        )
        rendered = render_prompt(
            PROMPT_TEMPLATE,
            PROMPT_VERSION,
            {
                "dimension": dimension,
                "description": description,
                "context": _render_context(snippets),
            },
        )
        response_schema = AIRequirementCandidateBatch.model_json_schema()

        system_prompt = rendered.system
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_latency_ms = 0
        last_model = ""
        last_error: Exception | None = None

        for _attempt in range(1, _MAX_GENERATION_ATTEMPTS + 1):
            response = self._provider.generate(
                AIRequest(
                    system_prompt=system_prompt,
                    user_prompt=rendered.user,
                    response_schema=response_schema,
                    max_tokens=_MAX_TOKENS,
                    temperature=_TEMPERATURE,
                    timeout_seconds=self._request_timeout_seconds,
                )
            )
            total_prompt_tokens += response.token_usage.prompt_tokens
            total_completion_tokens += response.token_usage.completion_tokens
            total_latency_ms += response.latency_ms
            last_model = response.model

            try:
                valid_candidates, dropped_count = _parse_candidates(response.parsed_output)
            except (ValidationError, _NoValidCandidatesError) as exc:
                last_error = exc
                system_prompt = (
                    f"{rendered.system}\n\nLa respuesta anterior no cumplio el schema JSON "
                    f"requerido ({exc}). Corrige el formato y responde nuevamente solo con "
                    "JSON valido."
                )
                continue

            candidates = [
                candidate.model_copy(update={"dimension": dimension})
                for candidate in valid_candidates
            ]
            token_usage = TokenUsage(
                prompt_tokens=total_prompt_tokens,
                completion_tokens=total_completion_tokens,
                total_tokens=total_prompt_tokens + total_completion_tokens,
            )
            return candidates, last_model, token_usage, total_latency_ms, dropped_count

        assert last_error is not None
        raise last_error

    def _estimate_cost(self, token_usage: TokenUsage) -> float | None:
        if self._prompt_price_per_1k is None or self._completion_price_per_1k is None:
            return None
        return (token_usage.prompt_tokens / 1000) * self._prompt_price_per_1k + (
            token_usage.completion_tokens / 1000
        ) * self._completion_price_per_1k

    def _resolve_requester(self, execution: AIExecution) -> ActorContext | None:
        try:
            return self._identity.resolve_actor_context(execution.requested_by_membership_id)
        except ActorNotFoundError:
            logger.warning("ai_execution_requester_not_found", extra={"execution_id": execution.id})
            return None

    def _record_success_audit(
        self, tenant_id: str, execution: AIExecution, candidate_count: int, dropped_count: int
    ) -> None:
        actor = self._resolve_requester(execution)
        if actor is None:
            return
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="ai_generation_succeeded",
            resource_type="ai_execution",
            resource_id=execution.id,
            evaluation_id=execution.evaluation_id,
            metadata={
                "candidate_count": candidate_count,
                "dropped_candidate_count": dropped_count,
                "prompt_version": execution.prompt_version,
            },
        )

    def _record_failure_audit(self, tenant_id: str, execution: AIExecution, error: str) -> None:
        actor = self._resolve_requester(execution)
        if actor is None:
            return
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="ai_generation_failed",
            resource_type="ai_execution",
            resource_id=execution.id,
            evaluation_id=execution.evaluation_id,
            metadata={"error_type": error[:200]},
        )


def _requirement_from_candidate(
    candidate: AIRequirementCandidate, display_order: int
) -> Requirement:
    return Requirement.create(
        dimension=candidate.dimension,
        category=candidate.category,
        title=candidate.title,
        description=candidate.description,
        priority=candidate.priority,
        response_type=candidate.response_type,
        weight=candidate.weight,
        required=candidate.required,
        display_order=display_order,
        buyer_guidance=candidate.buyer_guidance or None,
        options=candidate.options or None,
    )


def build_ai_service(settings: Settings, provider: AIProvider) -> AIService:
    """Single wiring point for `AIService` (ADR 0005: the worker must never
    duplicate/diverge from what the API would construct) - `ai.router`'s
    `get_ai_service` and `worker/main.py` both call this instead of each
    hand-assembling their own copy of the dependency graph."""
    db = get_database(settings)
    return AIService(
        executions=AIExecutionRepository(db),
        evaluations=EvaluationRepository(db),
        research=InternalKnowledgeProvider(
            KnowledgeTemplateRepository(db), EvaluationRepository(db)
        ),
        provider=provider,
        identity=IdentityService(
            TenantRepository(db), UserRepository(db), MembershipRepository(db)
        ),
        audit=AuditEventService(AuditEventRepository(db), settings),
        message_bus=get_message_bus(settings),
        retention_days=settings.ai_execution_retention_days,
        request_timeout_seconds=settings.ai_request_timeout_seconds,
        prompt_price_per_1k=settings.ai_prompt_price_per_1k_tokens_usd,
        completion_price_per_1k=settings.ai_completion_price_per_1k_tokens_usd,
    )
