from fastapi import APIRouter, Depends, HTTPException

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
from procurawise.vendor_portal.dependencies import require_agreements_accepted
from procurawise.vendor_portal.schemas import (
    AnswerWriteRequest,
    SubmitRequest,
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


def _detail(
    proposal: Proposal, evaluation_name: str, requirements: list[Requirement]
) -> VendorProposalDetailResponse:
    return VendorProposalDetailResponse(
        id=proposal.id,
        evaluation_id=proposal.evaluation_id,
        evaluation_name=evaluation_name,
        status=proposal.status,
        version=proposal.version,
        requirements=[_requirement_response(r) for r in requirements],
        answers=[
            VendorAnswerResponse(
                requirement_id=a.requirement_id,
                value=a.value,
                vendor_comment=a.vendor_comment,
                updated_at=a.updated_at,
            )
            for a in proposal.answers
        ],
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

    proposal, evaluation_name, requirements = service.get_proposal_with_requirements(
        context.tenant_id, context.vendor_org_id, proposal_id
    )
    return _detail(proposal, evaluation_name, requirements)
