from fastapi import APIRouter, Depends, HTTPException

from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.service import AuditEventService
from procurawise.documents.repository import DocumentRepository
from procurawise.evaluations.models import Requirement
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.evaluations.schemas import RequirementResponse
from procurawise.identity.repository import MembershipRepository, VendorOrganizationRepository
from procurawise.notifications.dependencies import build_notification_service
from procurawise.proposals.exceptions import (
    InvalidProposalTransitionError,
    InvalidReopenReasonError,
    ProposalAlreadyMaxRoundsError,
    ProposalNotFoundError,
    ProposalNotSubmittedError,
)
from procurawise.proposals.models import Proposal, ProposalAnswer, ProposalSnapshot
from procurawise.proposals.repository import ProposalRepository
from procurawise.proposals.schemas import (
    AnswerResponse,
    ProposalDetailResponse,
    ProposalSummaryResponse,
    ReopenProposalRequest,
    SnapshotCostItemResponse,
    SnapshotResponse,
)
from procurawise.proposals.service import ProposalService
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext, require_role
from procurawise.shared.mongo import get_database
from procurawise.shared.roles import BUYER_READ_ROLES, OWNER_ONLY
from procurawise.tco.models import CostItem, TcoResult
from procurawise.tco.repository import FXRateRepository
from procurawise.tco.schemas import FrozenFxRateResponse, TcoResultResponse

router = APIRouter(prefix="/evaluations/{evaluation_id}/proposals", tags=["proposals"])

require_buyer_read = require_role(*BUYER_READ_ROLES)
require_owner = require_role(*OWNER_ONLY)


def get_proposal_service(settings: Settings = Depends(get_settings)) -> ProposalService:
    db = get_database(settings)
    return ProposalService(
        proposals=ProposalRepository(db),
        evaluations=EvaluationRepository(db),
        vendor_orgs=VendorOrganizationRepository(db),
        memberships=MembershipRepository(db),
        audit=AuditEventService(AuditEventRepository(db), settings),
        documents=DocumentRepository(db),
        fx_rates=FXRateRepository(db),
        notifications=build_notification_service(settings),
    )


def get_evaluation_repository(settings: Settings = Depends(get_settings)) -> EvaluationRepository:
    return EvaluationRepository(get_database(settings))


def _summary(proposal: Proposal) -> ProposalSummaryResponse:
    return ProposalSummaryResponse(
        id=proposal.id,
        evaluation_id=proposal.evaluation_id,
        vendor_org_id=proposal.vendor_org_id,
        status=proposal.status,
        version=proposal.version,
        round=proposal.round,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
        submitted_at=proposal.submitted_at,
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


def _answer_response(answer: ProposalAnswer) -> AnswerResponse:
    return AnswerResponse(
        requirement_id=answer.requirement_id,
        value=answer.value,
        vendor_comment=answer.vendor_comment,
        updated_at=answer.updated_at,
        status=answer.status,
        source_proposal_version=answer.source_proposal_version,
    )


def _snapshot_cost_item_response(item: CostItem) -> SnapshotCostItemResponse:
    return SnapshotCostItemResponse(
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


def _snapshot_tco_result_response(result: TcoResult) -> TcoResultResponse:
    return TcoResultResponse(
        base_currency=result.base_currency,
        horizon_years=result.horizon_years,
        by_year={str(year): v for year, v in result.by_year.items()},
        by_year_with_tax={str(year): v for year, v in result.by_year_with_tax.items()},
        by_category=result.by_category,
        grand_total=result.grand_total,
        grand_total_with_tax=result.grand_total_with_tax,
        fx_rates_used=[
            FrozenFxRateResponse(
                from_currency=r.from_currency,
                to_currency=r.to_currency,
                rate=r.rate,
                effective_date=r.effective_date,
                source=r.source,
            )
            for r in result.fx_rates_used
        ],
        calculated_at=result.calculated_at,
    )


def _snapshot_response(snapshot: ProposalSnapshot) -> SnapshotResponse:
    return SnapshotResponse(
        snapshot_id=snapshot.snapshot_id,
        taken_at=snapshot.taken_at,
        evaluation_id=snapshot.evaluation_id,
        evaluation_name=snapshot.evaluation_name,
        vendor_org_id=snapshot.vendor_org_id,
        vendor_org_name=snapshot.vendor_org_name,
        requirements=[_requirement_response(r) for r in snapshot.requirements],
        answers=[_answer_response(a) for a in snapshot.answers],
        submitted_by_membership_id=snapshot.submitted_by_membership_id,
        submitted_at=snapshot.submitted_at,
        document_ids=snapshot.document_ids,
        round=snapshot.round,
        cost_items=[_snapshot_cost_item_response(c) for c in snapshot.cost_items],
        tco_result=(
            _snapshot_tco_result_response(snapshot.tco_result) if snapshot.tco_result else None
        ),
    )


def _detail(proposal: Proposal) -> ProposalDetailResponse:
    return ProposalDetailResponse(
        id=proposal.id,
        evaluation_id=proposal.evaluation_id,
        vendor_org_id=proposal.vendor_org_id,
        status=proposal.status,
        version=proposal.version,
        round=proposal.round,
        answers=[_answer_response(a) for a in proposal.answers],
        snapshots=[_snapshot_response(s) for s in proposal.snapshots],
        reopened_reason=proposal.reopened_reason,
        reopened_at=proposal.reopened_at,
        reopened_by_membership_id=proposal.reopened_by_membership_id,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
        submitted_at=proposal.submitted_at,
    )


@router.get("", response_model=list[ProposalSummaryResponse])
def list_proposals(
    evaluation_id: str,
    context: ActorContext = Depends(require_buyer_read),
    service: ProposalService = Depends(get_proposal_service),
    evaluations: EvaluationRepository = Depends(get_evaluation_repository),
) -> list[ProposalSummaryResponse]:
    if evaluations.find_by_id(context.tenant_id, evaluation_id) is None:
        raise HTTPException(status_code=404)
    return [_summary(p) for p in service.list_for_evaluation(context.tenant_id, evaluation_id)]


@router.get("/{proposal_id}", response_model=ProposalDetailResponse)
def get_proposal(
    evaluation_id: str,
    proposal_id: str,
    context: ActorContext = Depends(require_buyer_read),
    service: ProposalService = Depends(get_proposal_service),
) -> ProposalDetailResponse:
    try:
        proposal = service.get_proposal(context.tenant_id, proposal_id)
    except ProposalNotFoundError:
        raise HTTPException(status_code=404) from None
    if proposal.evaluation_id != evaluation_id:
        raise HTTPException(status_code=404)
    return _detail(proposal)


@router.post("/{proposal_id}/reopen", response_model=ProposalDetailResponse)
def reopen_proposal(
    evaluation_id: str,
    proposal_id: str,
    body: ReopenProposalRequest,
    context: ActorContext = Depends(require_owner),
    service: ProposalService = Depends(get_proposal_service),
) -> ProposalDetailResponse:
    """Fase 21 (ADR 0013, FR-047) - opens the single negotiation round the
    MVP allows for exactly this proposal; owner-only, one call per
    selected vendor (mirrors link_vendor's one-call-per-vendor convention).
    Proposals not reopened are untouched - they keep their last submitted
    snapshot as-is."""
    try:
        proposal = service.reopen(
            context.tenant_id,
            evaluation_id,
            proposal_id,
            body.reason,
            body.response_deadline,
            actor=context,
        )
    except ProposalNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidReopenReasonError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except InvalidProposalTransitionError:
        raise HTTPException(status_code=409, detail="evaluation is not evaluating") from None
    except ProposalNotSubmittedError:
        raise HTTPException(status_code=409, detail="proposal is not submitted") from None
    except ProposalAlreadyMaxRoundsError:
        raise HTTPException(
            status_code=409, detail="proposal already reached the maximum number of rounds"
        ) from None
    return _detail(proposal)
