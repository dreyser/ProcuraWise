from fastapi import APIRouter, Depends, HTTPException

from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.service import AuditEventService
from procurawise.documents.repository import DocumentRepository
from procurawise.evaluations.models import Requirement
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.evaluations.schemas import RequirementResponse
from procurawise.identity.repository import VendorOrganizationRepository
from procurawise.proposals.exceptions import ProposalNotFoundError
from procurawise.proposals.models import Proposal
from procurawise.proposals.repository import ProposalRepository
from procurawise.proposals.schemas import (
    AnswerResponse,
    ProposalDetailResponse,
    ProposalSummaryResponse,
    SnapshotResponse,
)
from procurawise.proposals.service import ProposalService
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext, require_role
from procurawise.shared.mongo import get_database
from procurawise.shared.roles import BUYER_READ_ROLES
from procurawise.tco.repository import FXRateRepository

router = APIRouter(prefix="/evaluations/{evaluation_id}/proposals", tags=["proposals"])

require_buyer_read = require_role(*BUYER_READ_ROLES)


def get_proposal_service(settings: Settings = Depends(get_settings)) -> ProposalService:
    db = get_database(settings)
    return ProposalService(
        proposals=ProposalRepository(db),
        evaluations=EvaluationRepository(db),
        vendor_orgs=VendorOrganizationRepository(db),
        audit=AuditEventService(AuditEventRepository(db), settings),
        documents=DocumentRepository(db),
        fx_rates=FXRateRepository(db),
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


def _detail(proposal: Proposal) -> ProposalDetailResponse:
    snapshot = None
    if proposal.snapshot is not None:
        snapshot = SnapshotResponse(
            snapshot_id=proposal.snapshot.snapshot_id,
            taken_at=proposal.snapshot.taken_at,
            evaluation_id=proposal.snapshot.evaluation_id,
            evaluation_name=proposal.snapshot.evaluation_name,
            vendor_org_id=proposal.snapshot.vendor_org_id,
            vendor_org_name=proposal.snapshot.vendor_org_name,
            requirements=[_requirement_response(r) for r in proposal.snapshot.requirements],
            answers=[
                AnswerResponse(
                    requirement_id=a.requirement_id,
                    value=a.value,
                    vendor_comment=a.vendor_comment,
                    updated_at=a.updated_at,
                )
                for a in proposal.snapshot.answers
            ],
            submitted_by_membership_id=proposal.snapshot.submitted_by_membership_id,
            submitted_at=proposal.snapshot.submitted_at,
            document_ids=proposal.snapshot.document_ids,
        )
    return ProposalDetailResponse(
        id=proposal.id,
        evaluation_id=proposal.evaluation_id,
        vendor_org_id=proposal.vendor_org_id,
        status=proposal.status,
        version=proposal.version,
        answers=[
            AnswerResponse(
                requirement_id=a.requirement_id,
                value=a.value,
                vendor_comment=a.vendor_comment,
                updated_at=a.updated_at,
            )
            for a in proposal.answers
        ],
        snapshot=snapshot,
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
