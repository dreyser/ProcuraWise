from fastapi import APIRouter, Depends, HTTPException, Query

from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.service import AuditEventService
from procurawise.documents.repository import DocumentRepository
from procurawise.evaluations.exceptions import RequirementNotFoundError
from procurawise.evaluations.models import Requirement
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.repository import VendorOrganizationRepository
from procurawise.proposals.exceptions import (
    AnswerValidationError,
    IncompleteRequiredAnswersError,
    InvalidProposalTransitionError,
    ProposalNotFoundError,
    StaleVersionError,
)
from procurawise.proposals.models import Proposal
from procurawise.proposals.repository import ProposalRepository
from procurawise.proposals.service import ProposalService
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext
from procurawise.shared.mongo import get_database
from procurawise.tco.exceptions import (
    CostItemNotFoundError,
    InvalidCostItemError,
    MissingFxRateError,
)
from procurawise.tco.models import CostItem, TcoResult
from procurawise.tco.repository import FXRateRepository
from procurawise.vendor_portal.dependencies import require_agreements_accepted
from procurawise.vendor_portal.schemas import (
    AnswerWriteRequest,
    CostItemResponse,
    CostItemUpdateRequest,
    CostItemWriteRequest,
    SubmitRequest,
    TcoPreviewResponse,
    VendorAnswerResponse,
    VendorProposalDetailResponse,
    VendorProposalSummaryResponse,
    VendorRequirementResponse,
)
from procurawise.vendor_portal.service import VendorPortalService

router = APIRouter(prefix="/vendor-portal/proposals", tags=["vendor-portal"])


def get_vendor_portal_service(settings: Settings = Depends(get_settings)) -> VendorPortalService:
    db = get_database(settings)
    proposals_service = ProposalService(
        proposals=ProposalRepository(db),
        evaluations=EvaluationRepository(db),
        vendor_orgs=VendorOrganizationRepository(db),
        audit=AuditEventService(AuditEventRepository(db), settings),
        documents=DocumentRepository(db),
        fx_rates=FXRateRepository(db),
    )
    return VendorPortalService(proposals=proposals_service, evaluations=EvaluationRepository(db))


def _requirement_response(requirement: Requirement) -> VendorRequirementResponse:
    return VendorRequirementResponse(
        id=requirement.id,
        dimension=requirement.dimension,
        category=requirement.category,
        title=requirement.title,
        description=requirement.description,
        priority=requirement.priority,
        response_type=requirement.response_type,
        required=requirement.required,
        buyer_guidance=requirement.buyer_guidance,
        display_order=requirement.display_order,
        options=requirement.options,
    )


def _cost_item_response(item: CostItem) -> CostItemResponse:
    return CostItemResponse(
        id=item.id,
        concept=item.concept,
        category=item.category,
        description=item.description,
        billing_unit=item.billing_unit,
        quantity=item.quantity,
        unit_price=item.unit_price,
        currency=item.currency,
        frequency_per_year=item.frequency_per_year,
        tax_pct=item.tax_pct,
        discount_pct=item.discount_pct,
        year_start=item.year_start,
        year_end=item.year_end,
        annual_increment_pct=item.annual_increment_pct,
        mandatory=item.mandatory,
        cost_type=item.cost_type,
        notes=item.notes,
        created_at=item.created_at,
        updated_at=item.updated_at,
        status=item.status,
        source_proposal_version=item.source_proposal_version,
    )


def _tco_preview_response(result: TcoResult) -> TcoPreviewResponse:
    return TcoPreviewResponse(
        base_currency=result.base_currency,
        horizon_years=result.horizon_years,
        by_year={str(year): v for year, v in result.by_year.items()},
        by_year_with_tax={str(year): v for year, v in result.by_year_with_tax.items()},
        by_category=result.by_category,
        grand_total=result.grand_total,
        grand_total_with_tax=result.grand_total_with_tax,
    )


def _detail(
    proposal: Proposal, evaluation_name: str, requirements: list[Requirement]
) -> VendorProposalDetailResponse:
    return VendorProposalDetailResponse(
        id=proposal.id,
        evaluation_id=proposal.evaluation_id,
        evaluation_name=evaluation_name,
        status=proposal.status,
        version=proposal.version,
        round=proposal.round,
        requirements=[_requirement_response(r) for r in requirements],
        answers=[
            VendorAnswerResponse(
                requirement_id=a.requirement_id,
                value=a.value,
                vendor_comment=a.vendor_comment,
                updated_at=a.updated_at,
                status=a.status,
                source_proposal_version=a.source_proposal_version,
            )
            for a in proposal.answers
        ],
        cost_items=[_cost_item_response(c) for c in proposal.cost_items],
        reopened_reason=proposal.reopened_reason,
        reopened_at=proposal.reopened_at,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
        submitted_at=proposal.submitted_at,
    )


def _summary(proposal: Proposal, evaluation_name: str) -> VendorProposalSummaryResponse:
    return VendorProposalSummaryResponse(
        id=proposal.id,
        evaluation_id=proposal.evaluation_id,
        evaluation_name=evaluation_name,
        status=proposal.status,
        version=proposal.version,
        round=proposal.round,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
        submitted_at=proposal.submitted_at,
    )


@router.get("", response_model=list[VendorProposalSummaryResponse])
def list_proposals(
    context: ActorContext = Depends(require_agreements_accepted),
    service: VendorPortalService = Depends(get_vendor_portal_service),
) -> list[VendorProposalSummaryResponse]:
    assert context.vendor_org_id is not None
    return [
        _summary(proposal, evaluation_name)
        for proposal, evaluation_name in service.list_proposals(
            context.tenant_id, context.vendor_org_id
        )
    ]


@router.get("/{proposal_id}", response_model=VendorProposalDetailResponse)
def get_proposal(
    proposal_id: str,
    context: ActorContext = Depends(require_agreements_accepted),
    service: VendorPortalService = Depends(get_vendor_portal_service),
) -> VendorProposalDetailResponse:
    assert context.vendor_org_id is not None
    try:
        proposal, evaluation_name, requirements = service.get_proposal_with_requirements(
            context.tenant_id, context.vendor_org_id, proposal_id
        )
    except ProposalNotFoundError:
        raise HTTPException(status_code=404) from None
    return _detail(proposal, evaluation_name, requirements)


@router.put("/{proposal_id}/answers/{requirement_id}", response_model=VendorProposalDetailResponse)
def update_answer(
    proposal_id: str,
    requirement_id: str,
    body: AnswerWriteRequest,
    context: ActorContext = Depends(require_agreements_accepted),
    service: VendorPortalService = Depends(get_vendor_portal_service),
) -> VendorProposalDetailResponse:
    assert context.vendor_org_id is not None
    try:
        service.update_answer(
            context.tenant_id,
            context.vendor_org_id,
            proposal_id,
            requirement_id,
            body.value,
            body.vendor_comment,
            body.expected_version,
        )
    except ProposalNotFoundError:
        raise HTTPException(status_code=404) from None
    except RequirementNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidProposalTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except StaleVersionError:
        raise HTTPException(status_code=409, detail="stale version") from None
    except AnswerValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    proposal, evaluation_name, requirements = service.get_proposal_with_requirements(
        context.tenant_id, context.vendor_org_id, proposal_id
    )
    return _detail(proposal, evaluation_name, requirements)


@router.post("/{proposal_id}/submit", response_model=VendorProposalDetailResponse)
def submit_proposal(
    proposal_id: str,
    body: SubmitRequest,
    context: ActorContext = Depends(require_agreements_accepted),
    service: VendorPortalService = Depends(get_vendor_portal_service),
) -> VendorProposalDetailResponse:
    assert context.vendor_org_id is not None
    try:
        service.submit(
            context.tenant_id,
            context.vendor_org_id,
            proposal_id,
            body.expected_version,
            context.membership_id,
            actor=context,
        )
    except ProposalNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidProposalTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except StaleVersionError:
        raise HTTPException(status_code=409, detail="stale version") from None
    except IncompleteRequiredAnswersError as exc:
        raise HTTPException(status_code=400, detail=f"missing required answers: {exc}") from None
    except MissingFxRateError as exc:
        raise HTTPException(status_code=422, detail=f"no fx rate available for {exc}") from None

    proposal, evaluation_name, requirements = service.get_proposal_with_requirements(
        context.tenant_id, context.vendor_org_id, proposal_id
    )
    return _detail(proposal, evaluation_name, requirements)


@router.post("/{proposal_id}/cost-items", response_model=VendorProposalDetailResponse)
def add_cost_item(
    proposal_id: str,
    body: CostItemWriteRequest,
    context: ActorContext = Depends(require_agreements_accepted),
    service: VendorPortalService = Depends(get_vendor_portal_service),
) -> VendorProposalDetailResponse:
    assert context.vendor_org_id is not None
    try:
        service.add_cost_item(
            context.tenant_id,
            context.vendor_org_id,
            proposal_id,
            body.expected_version,
            concept=body.concept,
            category=body.category,
            description=body.description,
            billing_unit=body.billing_unit,
            quantity=body.quantity,
            unit_price=body.unit_price,
            currency=body.currency,
            frequency_per_year=body.frequency_per_year,
            tax_pct=body.tax_pct,
            discount_pct=body.discount_pct,
            year_start=body.year_start,
            year_end=body.year_end,
            annual_increment_pct=body.annual_increment_pct,
            mandatory=body.mandatory,
            cost_type=body.cost_type,
            notes=body.notes,
        )
    except ProposalNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidProposalTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except StaleVersionError:
        raise HTTPException(status_code=409, detail="stale version") from None
    except InvalidCostItemError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    proposal, evaluation_name, requirements = service.get_proposal_with_requirements(
        context.tenant_id, context.vendor_org_id, proposal_id
    )
    return _detail(proposal, evaluation_name, requirements)


@router.put("/{proposal_id}/cost-items/{cost_item_id}", response_model=VendorProposalDetailResponse)
def update_cost_item(
    proposal_id: str,
    cost_item_id: str,
    body: CostItemUpdateRequest,
    context: ActorContext = Depends(require_agreements_accepted),
    service: VendorPortalService = Depends(get_vendor_portal_service),
) -> VendorProposalDetailResponse:
    assert context.vendor_org_id is not None
    fields = body.model_dump(exclude={"expected_version"})
    try:
        service.update_cost_item(
            context.tenant_id,
            context.vendor_org_id,
            proposal_id,
            cost_item_id,
            body.expected_version,
            **fields,
        )
    except ProposalNotFoundError:
        raise HTTPException(status_code=404) from None
    except CostItemNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidProposalTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except StaleVersionError:
        raise HTTPException(status_code=409, detail="stale version") from None
    except InvalidCostItemError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    proposal, evaluation_name, requirements = service.get_proposal_with_requirements(
        context.tenant_id, context.vendor_org_id, proposal_id
    )
    return _detail(proposal, evaluation_name, requirements)


@router.delete(
    "/{proposal_id}/cost-items/{cost_item_id}",
    response_model=VendorProposalDetailResponse,
)
def remove_cost_item(
    proposal_id: str,
    cost_item_id: str,
    expected_version: int = Query(...),
    context: ActorContext = Depends(require_agreements_accepted),
    service: VendorPortalService = Depends(get_vendor_portal_service),
) -> VendorProposalDetailResponse:
    assert context.vendor_org_id is not None
    try:
        service.remove_cost_item(
            context.tenant_id,
            context.vendor_org_id,
            proposal_id,
            cost_item_id,
            expected_version,
        )
    except ProposalNotFoundError:
        raise HTTPException(status_code=404) from None
    except CostItemNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidProposalTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except StaleVersionError:
        raise HTTPException(status_code=409, detail="stale version") from None

    proposal, evaluation_name, requirements = service.get_proposal_with_requirements(
        context.tenant_id, context.vendor_org_id, proposal_id
    )
    return _detail(proposal, evaluation_name, requirements)


@router.get("/{proposal_id}/tco-preview", response_model=TcoPreviewResponse)
def preview_tco(
    proposal_id: str,
    context: ActorContext = Depends(require_agreements_accepted),
    service: VendorPortalService = Depends(get_vendor_portal_service),
) -> TcoPreviewResponse:
    assert context.vendor_org_id is not None
    try:
        result = service.preview_tco(context.tenant_id, context.vendor_org_id, proposal_id)
    except ProposalNotFoundError:
        raise HTTPException(status_code=404) from None
    except MissingFxRateError as exc:
        raise HTTPException(status_code=422, detail=f"no fx rate available for {exc}") from None
    return _tco_preview_response(result)
