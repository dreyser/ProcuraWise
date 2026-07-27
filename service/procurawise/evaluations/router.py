from fastapi import APIRouter, Depends, HTTPException

from procurawise.evaluations.exceptions import (
    EvaluationNotFoundError,
    InvalidTransitionError,
    RequirementNotFoundError,
    StartCollectionPreconditionError,
    VendorAlreadyLinkedError,
    VendorLimitExceededError,
    VendorNotLinkedError,
    VendorOrganizationNotFoundError,
)
from procurawise.evaluations.models import Evaluation, Requirement
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.evaluations.schemas import (
    EvaluationCreateRequest,
    EvaluationDetailResponse,
    EvaluationSummaryResponse,
    EvaluationUpdateRequest,
    RequirementCreateRequest,
    RequirementResponse,
    RequirementUpdateRequest,
    VendorLinkRequest,
)
from procurawise.evaluations.service import EvaluationService
from procurawise.identity.repository import VendorOrganizationRepository
from procurawise.proposals.repository import ProposalRepository
from procurawise.proposals.schemas import ProposalSummaryResponse
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext, require_role
from procurawise.shared.mongo import get_database

router = APIRouter(prefix="/evaluations", tags=["evaluations"])

BUYER_READ_ROLES = ("evaluation_owner", "evaluator")
OWNER_ONLY = ("evaluation_owner",)

# Computed once at module import time (not inside a route's argument default,
# which ruff/bugbear (B008) flags as a function call in a mutable default) -
# FastAPI still resolves this dependency fresh on every request.
require_buyer_read = require_role(*BUYER_READ_ROLES)
require_owner = require_role(*OWNER_ONLY)


def get_evaluation_service(settings: Settings = Depends(get_settings)) -> EvaluationService:
    db = get_database(settings)
    return EvaluationService(
        evaluations=EvaluationRepository(db),
        proposals=ProposalRepository(db),
        vendor_orgs=VendorOrganizationRepository(db),
    )


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


def _evaluation_detail(evaluation: Evaluation) -> EvaluationDetailResponse:
    return EvaluationDetailResponse(
        id=evaluation.id,
        name=evaluation.name,
        description=evaluation.description,
        status=evaluation.status,
        requirements=[_requirement_response(r) for r in evaluation.requirements],
        linked_vendor_count=evaluation.linked_vendor_count,
        created_by_membership_id=evaluation.created_by_membership_id,
        created_at=evaluation.created_at,
        updated_at=evaluation.updated_at,
        collecting_responses_started_at=evaluation.collecting_responses_started_at,
        evaluating_started_at=evaluation.evaluating_started_at,
        completed_at=evaluation.completed_at,
    )


@router.post("", response_model=EvaluationDetailResponse, status_code=201)
def create_evaluation(
    body: EvaluationCreateRequest,
    context: ActorContext = Depends(require_owner),
    service: EvaluationService = Depends(get_evaluation_service),
) -> EvaluationDetailResponse:
    evaluation = service.create_evaluation(
        context.tenant_id, context.membership_id, body.name, body.description
    )
    return _evaluation_detail(evaluation)


@router.get("", response_model=list[EvaluationSummaryResponse])
def list_evaluations(
    context: ActorContext = Depends(require_buyer_read),
    service: EvaluationService = Depends(get_evaluation_service),
) -> list[EvaluationSummaryResponse]:
    return [
        EvaluationSummaryResponse(
            id=e.id,
            name=e.name,
            status=e.status,
            linked_vendor_count=e.linked_vendor_count,
            created_at=e.created_at,
            updated_at=e.updated_at,
        )
        for e in service.list_evaluations(context.tenant_id)
    ]


@router.get("/{evaluation_id}", response_model=EvaluationDetailResponse)
def get_evaluation(
    evaluation_id: str,
    context: ActorContext = Depends(require_buyer_read),
    service: EvaluationService = Depends(get_evaluation_service),
) -> EvaluationDetailResponse:
    try:
        evaluation = service.get_evaluation(context.tenant_id, evaluation_id)
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    return _evaluation_detail(evaluation)


@router.patch("/{evaluation_id}", response_model=EvaluationDetailResponse)
def update_evaluation(
    evaluation_id: str,
    body: EvaluationUpdateRequest,
    context: ActorContext = Depends(require_owner),
    service: EvaluationService = Depends(get_evaluation_service),
) -> EvaluationDetailResponse:
    try:
        evaluation = service.update_evaluation(
            context.tenant_id, evaluation_id, body.name, body.description
        )
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidTransitionError:
        raise HTTPException(status_code=409, detail="evaluation is not draft") from None
    return _evaluation_detail(evaluation)


@router.post("/{evaluation_id}/requirements", response_model=RequirementResponse, status_code=201)
def add_requirement(
    evaluation_id: str,
    body: RequirementCreateRequest,
    context: ActorContext = Depends(require_owner),
    service: EvaluationService = Depends(get_evaluation_service),
) -> RequirementResponse:
    try:
        requirement = service.add_requirement(
            context.tenant_id,
            evaluation_id,
            dimension=body.dimension,
            category=body.category,
            title=body.title,
            description=body.description,
            priority=body.priority,
            response_type=body.response_type,
            weight=body.weight,
            required=body.required,
            display_order=body.display_order,
            buyer_guidance=body.buyer_guidance,
            options=body.options,
        )
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidTransitionError:
        raise HTTPException(status_code=409, detail="evaluation is not draft") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _requirement_response(requirement)


@router.patch("/{evaluation_id}/requirements/{requirement_id}", response_model=RequirementResponse)
def update_requirement(
    evaluation_id: str,
    requirement_id: str,
    body: RequirementUpdateRequest,
    context: ActorContext = Depends(require_owner),
    service: EvaluationService = Depends(get_evaluation_service),
) -> RequirementResponse:
    field_updates = body.model_dump(exclude_unset=True)
    try:
        requirement = service.update_requirement(
            context.tenant_id, evaluation_id, requirement_id, field_updates
        )
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except RequirementNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidTransitionError:
        raise HTTPException(status_code=409, detail="evaluation is not draft") from None
    return _requirement_response(requirement)


@router.delete("/{evaluation_id}/requirements/{requirement_id}", status_code=204)
def delete_requirement(
    evaluation_id: str,
    requirement_id: str,
    context: ActorContext = Depends(require_owner),
    service: EvaluationService = Depends(get_evaluation_service),
) -> None:
    try:
        service.delete_requirement(context.tenant_id, evaluation_id, requirement_id)
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except RequirementNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidTransitionError:
        raise HTTPException(status_code=409, detail="evaluation is not draft") from None


@router.post("/{evaluation_id}/vendors", response_model=ProposalSummaryResponse, status_code=201)
def link_vendor(
    evaluation_id: str,
    body: VendorLinkRequest,
    context: ActorContext = Depends(require_owner),
    service: EvaluationService = Depends(get_evaluation_service),
) -> ProposalSummaryResponse:
    try:
        proposal = service.link_vendor(context.tenant_id, evaluation_id, body.vendor_org_id)
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except VendorOrganizationNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidTransitionError:
        raise HTTPException(status_code=409, detail="evaluation is not draft") from None
    except VendorLimitExceededError:
        raise HTTPException(status_code=400, detail="maximum of 6 linked vendors reached") from None
    except VendorAlreadyLinkedError:
        raise HTTPException(status_code=409, detail="vendor already linked") from None
    return ProposalSummaryResponse(
        id=proposal.id,
        evaluation_id=proposal.evaluation_id,
        vendor_org_id=proposal.vendor_org_id,
        status=proposal.status,
        version=proposal.version,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
        submitted_at=proposal.submitted_at,
    )


@router.delete("/{evaluation_id}/vendors/{vendor_org_id}", status_code=204)
def unlink_vendor(
    evaluation_id: str,
    vendor_org_id: str,
    context: ActorContext = Depends(require_owner),
    service: EvaluationService = Depends(get_evaluation_service),
) -> None:
    try:
        service.unlink_vendor(context.tenant_id, evaluation_id, vendor_org_id)
    except VendorNotLinkedError:
        raise HTTPException(status_code=404) from None
    except InvalidTransitionError:
        raise HTTPException(status_code=409) from None


@router.post("/{evaluation_id}/start-collection", response_model=EvaluationDetailResponse)
def start_collection(
    evaluation_id: str,
    context: ActorContext = Depends(require_owner),
    service: EvaluationService = Depends(get_evaluation_service),
) -> EvaluationDetailResponse:
    try:
        evaluation = service.start_collection(context.tenant_id, evaluation_id)
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidTransitionError:
        raise HTTPException(status_code=409, detail="evaluation is not draft") from None
    except StartCollectionPreconditionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _evaluation_detail(evaluation)


@router.post("/{evaluation_id}/start-evaluation", response_model=EvaluationDetailResponse)
def start_evaluation(
    evaluation_id: str,
    context: ActorContext = Depends(require_owner),
    service: EvaluationService = Depends(get_evaluation_service),
) -> EvaluationDetailResponse:
    try:
        evaluation = service.start_evaluation(context.tenant_id, evaluation_id)
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidTransitionError:
        raise HTTPException(
            status_code=409, detail="evaluation is not collecting_responses"
        ) from None
    return _evaluation_detail(evaluation)
