from fastapi import APIRouter, Depends, HTTPException

from procurawise.ai.exceptions import (
    AIExecutionNotFoundError,
    InvalidAIExecutionStateError,
    InvalidCandidateSelectionError,
)
from procurawise.ai.models import AIExecution
from procurawise.ai.provider import AIProvider, resolve_ai_provider
from procurawise.ai.schemas import (
    AcceptSuggestionsRequest,
    AcceptSuggestionsResponse,
    AIRequirementCandidate,
    AIScoreSuggestionCandidate,
    ResearchSnippetResponse,
    ResearchWarningResponse,
    ScoreSuggestionJobStatusResponse,
    SuggestionJobStatusResponse,
    TokenUsageResponse,
    TriggerScoreSuggestionRequest,
    TriggerSuggestionRequest,
    TriggerSuggestionResponse,
)
from procurawise.ai.service import AIService, build_ai_service
from procurawise.evaluations.exceptions import EvaluationNotFoundError, InvalidTransitionError
from procurawise.evaluations.models import Requirement
from procurawise.evaluations.schemas import RequirementResponse
from procurawise.proposals.exceptions import ProposalNotFoundError
from procurawise.scoring.exceptions import (
    RequirementNotInSnapshotError,
    ScoringPreconditionError,
    SectionNotAssignedToActorError,
)
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext, require_role
from procurawise.shared.roles import BUYER_READ_ROLES, OWNER_ONLY, SCORE_WRITE_ROLES

router = APIRouter(prefix="/evaluations/{evaluation_id}/ai", tags=["ai"])

# Fase 18 (ADR 0022): a second router in the same module, same precedent as
# qna/router.py (two routers, one file) - score-suggestion jobs are scoped
# to a proposal, not just an evaluation, so they need their own path prefix
# rather than forcing proposal_id into the existing `router` above.
score_suggestion_router = APIRouter(
    prefix="/evaluations/{evaluation_id}/proposals/{proposal_id}/ai", tags=["ai"]
)

require_buyer_read = require_role(*BUYER_READ_ROLES)
require_owner = require_role(*OWNER_ONLY)
require_score_write = require_role(*SCORE_WRITE_ROLES)


def get_ai_provider(settings: Settings = Depends(get_settings)) -> AIProvider:
    """Separate dependency, not folded into get_ai_service - tests override
    this one function (same shape as FakeOidcProvider's
    `app.dependency_overrides[get_oidc_provider]`) rather than reconstructing
    the whole service by hand."""
    return resolve_ai_provider(settings)


def get_ai_service(
    settings: Settings = Depends(get_settings),
    provider: AIProvider = Depends(get_ai_provider),
) -> AIService:
    return build_ai_service(settings, provider)


def _requirement_response(requirement: Requirement) -> RequirementResponse:
    return RequirementResponse(
        id=requirement.id,
        dimension=requirement.dimension,
        category=requirement.category,
        title=requirement.title,
        description=requirement.description,
        priority=requirement.priority,
        response_type=requirement.response_type,
        weight=requirement.weight,
        required=requirement.required,
        buyer_guidance=requirement.buyer_guidance,
        display_order=requirement.display_order,
        options=requirement.options,
        created_at=requirement.created_at,
        updated_at=requirement.updated_at,
    )


def _status_response(execution: AIExecution) -> SuggestionJobStatusResponse:
    return SuggestionJobStatusResponse(
        job_id=execution.id,
        status=execution.status,
        candidates=(
            [AIRequirementCandidate.model_validate(c) for c in execution.candidates]
            if execution.candidates is not None
            else None
        ),
        error=execution.error,
        model=execution.model,
        prompt_version=execution.prompt_version,
        token_usage=(
            TokenUsageResponse(**execution.token_usage.to_document())
            if execution.token_usage is not None
            else None
        ),
        cost_estimate=execution.cost_estimate,
        latency_ms=execution.latency_ms,
        accepted_requirement_ids=execution.accepted_requirement_ids,
        # Fase 14: mapped straight from the persisted, immutable snapshot -
        # never re-derived from the live curated_sources collection.
        source_catalog=[
            ResearchSnippetResponse(
                source_type=doc["source_type"],
                source_id=doc["source_id"],
                title=doc["title"],
                url=doc.get("url"),
                retrieved_at=doc.get("retrieved_at"),
            )
            for doc in execution.source_catalog
        ],
        warnings=[
            ResearchWarningResponse(
                code=doc["code"], source_type=doc["source_type"], message=doc["message"]
            )
            for doc in execution.warnings
        ],
    )


@router.post("/requirement-suggestions", response_model=TriggerSuggestionResponse, status_code=202)
def trigger_requirement_suggestions(
    evaluation_id: str,
    body: TriggerSuggestionRequest,
    context: ActorContext = Depends(require_owner),
    service: AIService = Depends(get_ai_service),
) -> TriggerSuggestionResponse:
    """Fase 13 (ADR 0021/0012): returns 202 immediately - the worker's
    dispatch loop processes the job asynchronously, never this request."""
    try:
        execution = service.request_generation(
            context.tenant_id,
            evaluation_id,
            dimension=body.dimension,
            description=body.description,
            actor=context,
        )
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidTransitionError:
        raise HTTPException(status_code=409, detail="evaluation is not draft") from None
    status_url = f"/api/v1/evaluations/{evaluation_id}/ai/requirement-suggestions/{execution.id}"
    return TriggerSuggestionResponse(job_id=execution.id, status_url=status_url)


@router.get("/requirement-suggestions/{job_id}", response_model=SuggestionJobStatusResponse)
def get_requirement_suggestion_status(
    evaluation_id: str,
    job_id: str,
    context: ActorContext = Depends(require_buyer_read),
    service: AIService = Depends(get_ai_service),
) -> SuggestionJobStatusResponse:
    try:
        execution = service.get_execution(context.tenant_id, evaluation_id, job_id)
    except AIExecutionNotFoundError:
        raise HTTPException(status_code=404) from None
    return _status_response(execution)


@router.post(
    "/requirement-suggestions/{job_id}/accept",
    response_model=AcceptSuggestionsResponse,
    status_code=201,
)
def accept_requirement_suggestions(
    evaluation_id: str,
    job_id: str,
    body: AcceptSuggestionsRequest,
    context: ActorContext = Depends(require_owner),
    service: AIService = Depends(get_ai_service),
) -> AcceptSuggestionsResponse:
    try:
        added = service.accept_candidates(
            context.tenant_id,
            evaluation_id,
            job_id,
            body.candidate_indices,
            actor=context,
        )
    except (EvaluationNotFoundError, AIExecutionNotFoundError):
        raise HTTPException(status_code=404) from None
    except InvalidTransitionError:
        raise HTTPException(status_code=409, detail="evaluation is not draft") from None
    except InvalidAIExecutionStateError:
        raise HTTPException(status_code=409, detail="job has not succeeded yet") from None
    except InvalidCandidateSelectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return AcceptSuggestionsResponse(added_requirements=[_requirement_response(r) for r in added])


def _score_suggestion_status_response(execution: AIExecution) -> ScoreSuggestionJobStatusResponse:
    return ScoreSuggestionJobStatusResponse(
        job_id=execution.id,
        status=execution.status,
        candidates=(
            [AIScoreSuggestionCandidate.model_validate(c) for c in execution.candidates]
            if execution.candidates is not None
            else None
        ),
        error=execution.error,
        model=execution.model,
        prompt_version=execution.prompt_version,
        token_usage=(
            TokenUsageResponse(**execution.token_usage.to_document())
            if execution.token_usage is not None
            else None
        ),
        cost_estimate=execution.cost_estimate,
        latency_ms=execution.latency_ms,
    )


@score_suggestion_router.post(
    "/score-suggestions", response_model=TriggerSuggestionResponse, status_code=202
)
def trigger_score_suggestion(
    evaluation_id: str,
    proposal_id: str,
    body: TriggerScoreSuggestionRequest,
    context: ActorContext = Depends(require_score_write),
    service: AIService = Depends(get_ai_service),
) -> TriggerSuggestionResponse:
    """Fase 18 (ADR 0022): returns 202 immediately, same async contract as
    trigger_requirement_suggestions - the worker's dispatch loop processes
    the job, never this request. Never writes to `scores` - "aceptar o
    modificar" happens entirely through scoring.router.upsert_score."""
    try:
        execution = service.request_score_suggestion(
            context.tenant_id,
            evaluation_id,
            proposal_id,
            body.requirement_ids,
            actor=context,
        )
    except (EvaluationNotFoundError, ProposalNotFoundError):
        raise HTTPException(status_code=404) from None
    except ScoringPreconditionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except RequirementNotInSnapshotError:
        raise HTTPException(
            status_code=400, detail="requirement not in proposal snapshot"
        ) from None
    except SectionNotAssignedToActorError:
        raise HTTPException(
            status_code=403, detail="requirement's section is not assigned to this evaluator"
        ) from None
    status_url = (
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}"
        f"/ai/score-suggestions/{execution.id}"
    )
    return TriggerSuggestionResponse(job_id=execution.id, status_url=status_url)


@score_suggestion_router.get(
    "/score-suggestions/{job_id}", response_model=ScoreSuggestionJobStatusResponse
)
def get_score_suggestion_status(
    evaluation_id: str,
    proposal_id: str,
    job_id: str,
    context: ActorContext = Depends(require_buyer_read),
    service: AIService = Depends(get_ai_service),
) -> ScoreSuggestionJobStatusResponse:
    try:
        execution = service.get_score_suggestion_execution(
            context.tenant_id, evaluation_id, proposal_id, job_id
        )
    except AIExecutionNotFoundError:
        raise HTTPException(status_code=404) from None
    return _score_suggestion_status_response(execution)
