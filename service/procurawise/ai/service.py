import logging
from datetime import UTC, datetime

from pydantic import ValidationError

from procurawise.ai.composite_research_provider import build_research_provider
from procurawise.ai.exceptions import (
    AIExecutionNotFoundError,
    InvalidAIExecutionStateError,
    InvalidCandidateSelectionError,
)
from procurawise.ai.models import AIExecution, AIRequest, TokenUsage
from procurawise.ai.prompt_renderer import render_prompt
from procurawise.ai.provider import AIProvider
from procurawise.ai.repository import AIExecutionRepository
from procurawise.ai.research_provider import (
    DiscoveryQuery,
    ResearchProvider,
    ResearchSnippet,
    ResearchWarning,
)
from procurawise.ai.schemas import (
    AIRequirementCandidate,
    AIRequirementCandidateBatch,
    AIScoreSuggestionCandidate,
    AIScoreSuggestionCandidateBatch,
)
from procurawise.assignments.repository import AssignmentRepository
from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.service import AuditEventService
from procurawise.evaluations.exceptions import EvaluationNotFoundError, InvalidTransitionError
from procurawise.evaluations.models import Dimension, Evaluation, Requirement
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.repository import MembershipRepository, TenantRepository, UserRepository
from procurawise.identity.service import ActorNotFoundError, IdentityService
from procurawise.proposals.exceptions import ProposalNotFoundError
from procurawise.proposals.models import Proposal, ProposalAnswer
from procurawise.proposals.repository import ProposalRepository
from procurawise.scoring.exceptions import (
    RequirementNotInSnapshotError,
    ScoringPreconditionError,
    SectionNotAssignedToActorError,
)
from procurawise.scoring.service import enforce_section_assignment
from procurawise.shared.config import Settings
from procurawise.shared.context import ActorContext
from procurawise.shared.messaging import MessageBus, get_message_bus
from procurawise.shared.mongo import get_database

logger = logging.getLogger("procurawise.ai")

PROMPT_TEMPLATE = "requirement_generation"
# Fase 14 (ADR 0011): v2 adds source-id citation instructions to the prompt -
# v1 is left on disk, untouched, per ADR 0021's versioned-prompt discipline
# (never mutate a shipped prompt version in place).
PROMPT_VERSION = "v2"
JOB_TOPIC = "ai-requirement-generation"

_MAX_TOKENS = 2000
_MAX_GENERATION_ATTEMPTS = 2

# Fase 18 (ADR 0022): evaluacion asistida por IA - a second use_case sharing
# every other piece of this module's machinery (AIProvider, AIExecution,
# prompt_renderer, the retry-on-invalid-JSON loop) without duplicating it.
SCORE_SUGGESTION_PROMPT_TEMPLATE = "score_suggestion"
SCORE_SUGGESTION_PROMPT_VERSION = "v1"
SCORE_SUGGESTION_JOB_TOPIC = "ai-score-suggestion"
# Higher than requirement-generation's _MAX_TOKENS - a single job can cover
# every unscored requirement of a proposal's section, not just one item.
_SCORE_SUGGESTION_MAX_TOKENS = 3000


def _render_context(snippets: list[ResearchSnippet]) -> str:
    if not snippets:
        return "(sin contexto disponible)"
    # Fase 14: each line is prefixed with its source_id in brackets so the
    # v2 prompt can instruct the model to cite it in AIRequirementCandidate
    # .sources - the only way a citation ever gets attached to a candidate.
    return "\n".join(
        f"- [{snippet.source_id}] {snippet.title}: {snippet.content}" for snippet in snippets
    )


def _valid_source_ids(snippets: list[ResearchSnippet]) -> set[str]:
    return {snippet.source_id for snippet in snippets}


def _sanitize_candidate_sources(
    candidate: AIRequirementCandidate, valid_source_ids: set[str]
) -> AIRequirementCandidate | None:
    """Fase 14 (ADR 0011, founder decision): strips any source_id the model
    cited that isn't in this job's own source_catalog - unknown/invented ids
    never reach a user. A candidate that cited only invalid ids is dropped
    entirely rather than silently presented as uncited; a candidate with no
    sources at all (never claimed to be grounded) is left untouched."""
    if not candidate.sources:
        return candidate
    valid = [source_id for source_id in candidate.sources if source_id in valid_source_ids]
    if not valid:
        return None
    return candidate.model_copy(update={"sources": valid})


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


class _NoValidScoreCandidatesError(Exception):
    """Same role as _NoValidCandidatesError, for score-suggestion batches."""


def _parse_score_candidates(parsed_output: dict) -> tuple[list[AIScoreSuggestionCandidate], int]:
    raw_candidates = parsed_output.get("candidates")
    if not isinstance(raw_candidates, list):
        AIScoreSuggestionCandidateBatch.model_validate(parsed_output)
        raise AssertionError("unreachable - model_validate should have raised ValidationError")

    valid: list[AIScoreSuggestionCandidate] = []
    invalid_count = 0
    for raw_candidate in raw_candidates:
        try:
            valid.append(AIScoreSuggestionCandidate.model_validate(raw_candidate))
        except ValidationError:
            invalid_count += 1

    if not valid and raw_candidates:
        raise _NoValidScoreCandidatesError(
            f"all {len(raw_candidates)} candidates failed validation"
        )
    return valid, invalid_count


def _render_requirement_block(requirement: Requirement, answer: ProposalAnswer | None) -> str:
    value_text = (
        str(answer.value)
        if answer is not None and answer.value is not None
        else ("(sin respuesta)")
    )
    comment_text = (
        answer.vendor_comment
        if answer is not None and answer.vendor_comment
        else "(sin comentario)"
    )
    return (
        f"[{requirement.id}] {requirement.title}\n"
        f"Descripcion: {requirement.description}\n"
        f"Guia del comprador: {requirement.buyer_guidance or '(ninguna)'}\n"
        f'Respuesta del proveedor: """{value_text}"""\n'
        f'Comentario del proveedor: """{comment_text}"""'
    )


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
        proposals: ProposalRepository | None = None,
        assignments: AssignmentRepository | None = None,
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
        # Fase 18 (ADR 0022): only needed by the score_suggestion use case -
        # optional so existing callers that only ever trigger
        # requirement_generation (none left after build_ai_service is
        # updated, but kept optional for any lighter-weight test wiring)
        # don't need to construct them.
        self._proposals = proposals
        self._assignments = assignments

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
            (
                candidates,
                model,
                token_usage,
                latency_ms,
                dropped_count,
                snippets,
                warnings,
            ) = self._generate_candidates(
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
                "source_catalog": [snippet.to_document() for snippet in snippets],
                "warnings": [warning.to_document() for warning in warnings],
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
        # Fase 14 (ADR 0011, founder decision): re-validate source ids at
        # accept time too, not only at generation time - defense-in-depth
        # against a tampered/directly-edited AIExecution document. In
        # practice this is a no-op, since candidates are already sanitized
        # against this same catalog when persisted (_generate_candidates).
        valid_source_ids = {doc["source_id"] for doc in execution.source_catalog}

        next_display_order = len(evaluation.requirements) + 1
        new_requirements: list[Requirement] = []
        for offset, index in enumerate(candidate_indices):
            if index < 0 or index >= len(execution.candidates):
                raise InvalidCandidateSelectionError(f"candidate index {index} out of range")
            candidate = AIRequirementCandidate.model_validate(execution.candidates[index])
            sanitized = _sanitize_candidate_sources(candidate, valid_source_ids)
            if sanitized is None:
                raise InvalidCandidateSelectionError(
                    f"candidate at index {index} cites only unknown source ids"
                )
            try:
                new_requirements.append(
                    _requirement_from_candidate(sanitized, next_display_order + offset)
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

    def request_score_suggestion(
        self,
        tenant_id: str,
        evaluation_id: str,
        proposal_id: str,
        requirement_ids: list[str],
        *,
        actor: ActorContext,
    ) -> AIExecution:
        """Fase 18 (ADR 0022): triggers an async score-suggestion job for a
        submitted Proposal. Empty `requirement_ids` means "every requirement
        in the actor's assignable section(s) that already has a vendor
        answer and no Score yet" (resolved once, here, and passed through the
        message payload - never re-derived by the worker, same precedent as
        requirement_generation's dimension/description). Never writes to the
        `scores` collection - that stays exclusively ScoringService's job."""
        assert self._proposals is not None and self._assignments is not None
        evaluation = self._evaluating_evaluation_or_raise(tenant_id, evaluation_id)
        proposal = self._submitted_proposal_or_raise(tenant_id, proposal_id, evaluation_id)
        assert proposal.current_snapshot is not None

        target_requirements = self._resolve_score_suggestion_requirements(
            tenant_id, evaluation_id, proposal, requirement_ids, actor
        )
        target_requirement_ids = [r.id for r in target_requirements]

        execution = AIExecution.create(
            tenant_id=tenant_id,
            evaluation_id=evaluation.id,
            proposal_id=proposal_id,
            snapshot_id=proposal.current_snapshot.snapshot_id,
            requested_by_membership_id=actor.membership_id,
            use_case="score_suggestion",
            provider="azure_openai",
            prompt_template=SCORE_SUGGESTION_PROMPT_TEMPLATE,
            prompt_version=SCORE_SUGGESTION_PROMPT_VERSION,
            retention_days=self._retention_days,
        )
        self._executions.insert(tenant_id, execution.to_document())
        self._message_bus.publish(
            SCORE_SUGGESTION_JOB_TOPIC,
            {
                "tenant_id": tenant_id,
                "execution_id": execution.id,
                "requirement_ids": target_requirement_ids,
            },
        )
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="ai_score_suggestion_requested",
            resource_type="ai_execution",
            resource_id=execution.id,
            evaluation_id=evaluation_id,
            proposal_id=proposal_id,
            snapshot_id=proposal.current_snapshot.snapshot_id,
            metadata={
                "requirement_ids": target_requirement_ids,
                "prompt_template": SCORE_SUGGESTION_PROMPT_TEMPLATE,
                "prompt_version": SCORE_SUGGESTION_PROMPT_VERSION,
            },
        )
        return execution

    def get_score_suggestion_execution(
        self, tenant_id: str, evaluation_id: str, proposal_id: str, execution_id: str
    ) -> AIExecution:
        doc = self._executions.find_by_id(tenant_id, execution_id)
        if doc is None:
            raise AIExecutionNotFoundError(execution_id)
        execution = AIExecution.from_document(doc)
        if execution.evaluation_id != evaluation_id or execution.proposal_id != proposal_id:
            raise AIExecutionNotFoundError(execution_id)
        return execution

    def process_score_suggestion_job(
        self, tenant_id: str, execution_id: str, *, requirement_ids: list[str]
    ) -> None:
        doc = self._executions.find_by_id(tenant_id, execution_id)
        if doc is None:
            logger.error("ai_execution_not_found_for_job", extra={"execution_id": execution_id})
            return
        execution = AIExecution.from_document(doc)
        if execution.status != "queued":
            # Idempotency guard (ADR 0005), same as process_generation_job.
            return
        if not self._executions.transition_status(tenant_id, execution_id, "queued", "running"):
            return

        try:
            candidates, model, token_usage, latency_ms = self._generate_score_suggestions(
                tenant_id, execution, requirement_ids=requirement_ids
            )
        except Exception as exc:  # noqa: BLE001 - any provider/validation failure lands the job in `failed`, never crashes the worker loop
            logger.error(
                "ai_score_suggestion_failed",
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
            self._record_score_suggestion_failure_audit(tenant_id, execution, str(exc))
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
        self._record_score_suggestion_success_audit(tenant_id, execution, len(candidates))

    def _evaluating_evaluation_or_raise(self, tenant_id: str, evaluation_id: str) -> Evaluation:
        evaluation_doc = self._evaluations.find_by_id(tenant_id, evaluation_id)
        if evaluation_doc is None:
            raise EvaluationNotFoundError(evaluation_id)
        evaluation = Evaluation.from_document(evaluation_doc)
        if evaluation.status != "evaluating":
            raise ScoringPreconditionError("evaluation is not evaluating")
        return evaluation

    def _submitted_proposal_or_raise(
        self, tenant_id: str, proposal_id: str, evaluation_id: str
    ) -> Proposal:
        assert self._proposals is not None
        proposal_doc = self._proposals.find_by_id(tenant_id, proposal_id)
        if proposal_doc is None or proposal_doc["evaluation_id"] != evaluation_id:
            raise ProposalNotFoundError(proposal_id)
        proposal = Proposal.from_document(proposal_doc)
        if proposal.status != "submitted" or proposal.current_snapshot is None:
            raise ScoringPreconditionError("proposal is not submitted")
        return proposal

    def _resolve_score_suggestion_requirements(
        self,
        tenant_id: str,
        evaluation_id: str,
        proposal: Proposal,
        requirement_ids: list[str],
        actor: ActorContext,
    ) -> list[Requirement]:
        """Explicit ids: validated against the snapshot and the actor's
        assignment, raising if either check fails (the caller asked for
        something specific and can't have it). Empty list: silently
        narrowed to whatever the actor is allowed to score and already has
        an answer - the common "review my whole section" case."""
        assert self._assignments is not None and proposal.current_snapshot is not None
        requirements_by_id = {r.id: r for r in proposal.current_snapshot.requirements}
        answered_ids = {
            a.requirement_id for a in proposal.current_snapshot.answers if a.value is not None
        }

        if requirement_ids:
            selected: list[Requirement] = []
            for requirement_id in requirement_ids:
                requirement = requirements_by_id.get(requirement_id)
                if requirement is None:
                    raise RequirementNotInSnapshotError(requirement_id)
                enforce_section_assignment(
                    self._assignments,
                    tenant_id,
                    evaluation_id,
                    requirement.dimension,
                    requirement.category,
                    actor,
                )
                selected.append(requirement)
            return selected

        eligible: list[Requirement] = []
        for requirement in proposal.current_snapshot.requirements:
            if requirement.id not in answered_ids:
                continue
            try:
                enforce_section_assignment(
                    self._assignments,
                    tenant_id,
                    evaluation_id,
                    requirement.dimension,
                    requirement.category,
                    actor,
                )
            except SectionNotAssignedToActorError:
                continue
            eligible.append(requirement)
        return eligible

    def _generate_score_suggestions(
        self, tenant_id: str, execution: AIExecution, *, requirement_ids: list[str]
    ) -> tuple[list[AIScoreSuggestionCandidate], str, TokenUsage, int]:
        assert self._proposals is not None and execution.proposal_id is not None
        proposal_doc = self._proposals.find_by_id(tenant_id, execution.proposal_id)
        if proposal_doc is None:
            raise ProposalNotFoundError(execution.proposal_id)
        proposal = Proposal.from_document(proposal_doc)
        assert proposal.current_snapshot is not None
        requirements_by_id = {r.id: r for r in proposal.current_snapshot.requirements}
        answers_by_id = {a.requirement_id: a for a in proposal.current_snapshot.answers}

        blocks = [
            _render_requirement_block(requirements_by_id[rid], answers_by_id.get(rid))
            for rid in requirement_ids
            if rid in requirements_by_id
        ]
        rendered = render_prompt(
            SCORE_SUGGESTION_PROMPT_TEMPLATE,
            SCORE_SUGGESTION_PROMPT_VERSION,
            {"requirements_and_answers": "\n\n".join(blocks)},
        )
        response_schema = AIScoreSuggestionCandidateBatch.model_json_schema()

        system_prompt = rendered.system
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_latency_ms = 0
        last_model = ""
        last_error: Exception | None = None
        valid_requirement_ids = set(requirement_ids)

        for _attempt in range(1, _MAX_GENERATION_ATTEMPTS + 1):
            response = self._provider.generate(
                AIRequest(
                    system_prompt=system_prompt,
                    user_prompt=rendered.user,
                    response_schema=response_schema,
                    max_tokens=_SCORE_SUGGESTION_MAX_TOKENS,
                    timeout_seconds=self._request_timeout_seconds,
                )
            )
            total_prompt_tokens += response.token_usage.prompt_tokens
            total_completion_tokens += response.token_usage.completion_tokens
            total_latency_ms += response.latency_ms
            last_model = response.model

            try:
                valid_candidates, _dropped_count = _parse_score_candidates(response.parsed_output)
            except (ValidationError, _NoValidScoreCandidatesError) as exc:
                last_error = exc
                system_prompt = (
                    f"{rendered.system}\n\nLa respuesta anterior no cumplio el schema JSON "
                    f"requerido ({exc}). Corrige el formato y responde nuevamente solo con "
                    "JSON valido."
                )
                continue

            # Never trust a requirement_id the model invented - same
            # defense-in-depth principle as _sanitize_candidate_sources, and
            # drop duplicates (keep first occurrence) so a job never
            # produces two candidates for the same requirement.
            seen: set[str] = set()
            sanitized: list[AIScoreSuggestionCandidate] = []
            for candidate in valid_candidates:
                if candidate.requirement_id not in valid_requirement_ids:
                    continue
                if candidate.requirement_id in seen:
                    continue
                seen.add(candidate.requirement_id)
                sanitized.append(candidate)

            token_usage = TokenUsage(
                prompt_tokens=total_prompt_tokens,
                completion_tokens=total_completion_tokens,
                total_tokens=total_prompt_tokens + total_completion_tokens,
            )
            return sanitized, last_model, token_usage, total_latency_ms

        assert last_error is not None
        raise last_error

    def _record_score_suggestion_success_audit(
        self, tenant_id: str, execution: AIExecution, candidate_count: int
    ) -> None:
        actor = self._resolve_requester(execution)
        if actor is None:
            return
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="ai_score_suggestion_succeeded",
            resource_type="ai_execution",
            resource_id=execution.id,
            evaluation_id=execution.evaluation_id,
            proposal_id=execution.proposal_id,
            snapshot_id=execution.snapshot_id,
            metadata={
                "candidate_count": candidate_count,
                "prompt_version": execution.prompt_version,
            },
        )

    def _record_score_suggestion_failure_audit(
        self, tenant_id: str, execution: AIExecution, error: str
    ) -> None:
        actor = self._resolve_requester(execution)
        if actor is None:
            return
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="ai_score_suggestion_failed",
            resource_type="ai_execution",
            resource_id=execution.id,
            evaluation_id=execution.evaluation_id,
            proposal_id=execution.proposal_id,
            snapshot_id=execution.snapshot_id,
            metadata={"error_type": error[:200]},
        )

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
    ) -> tuple[
        list[AIRequirementCandidate],
        str,
        TokenUsage,
        int,
        int,
        list[ResearchSnippet],
        list[ResearchWarning],
    ]:
        discovery = self._research.discover(
            tenant_id,
            DiscoveryQuery(
                dimension=dimension,
                description=description,
                exclude_evaluation_id=execution.evaluation_id,
            ),
        )
        snippets = discovery.snippets
        warnings = discovery.warnings
        valid_source_ids = _valid_source_ids(snippets)
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
            # Fase 14 (ADR 0011, founder decision): strip/reject any cited
            # source_id that isn't in this job's own catalog before the
            # candidate is ever persisted - the only point where a citation
            # can be attached to AIExecution.candidates.
            sanitized_candidates: list[AIRequirementCandidate] = []
            source_forgery_drops = 0
            for candidate in candidates:
                sanitized = _sanitize_candidate_sources(candidate, valid_source_ids)
                if sanitized is None:
                    source_forgery_drops += 1
                    continue
                sanitized_candidates.append(sanitized)

            token_usage = TokenUsage(
                prompt_tokens=total_prompt_tokens,
                completion_tokens=total_completion_tokens,
                total_tokens=total_prompt_tokens + total_completion_tokens,
            )
            return (
                sanitized_candidates,
                last_model,
                token_usage,
                total_latency_ms,
                dropped_count + source_forgery_drops,
                snippets,
                warnings,
            )

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
        research=build_research_provider(settings, db),
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
        proposals=ProposalRepository(db),
        assignments=AssignmentRepository(db),
    )
