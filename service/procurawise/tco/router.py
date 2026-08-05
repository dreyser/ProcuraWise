from fastapi import APIRouter, Depends, HTTPException

from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.service import AuditEventService
from procurawise.documents.repository import DocumentRepository
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.repository import VendorOrganizationRepository
from procurawise.proposals.exceptions import ProposalNotFoundError
from procurawise.proposals.repository import ProposalRepository
from procurawise.proposals.service import ProposalService
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext, require_role
from procurawise.shared.mongo import get_database
from procurawise.shared.roles import BUYER_READ_ROLES
from procurawise.tco.models import TcoResult
from procurawise.tco.repository import FXRateRepository
from procurawise.tco.schemas import FrozenFxRateResponse, TcoResultResponse

router = APIRouter(prefix="/evaluations/{evaluation_id}/proposals/{proposal_id}/tco", tags=["tco"])

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


def _tco_result_response(result: TcoResult) -> TcoResultResponse:
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


@router.get("", response_model=TcoResultResponse)
def get_tco_result(
    evaluation_id: str,
    proposal_id: str,
    context: ActorContext = Depends(require_buyer_read),
    service: ProposalService = Depends(get_proposal_service),
) -> TcoResultResponse:
    """Fase 19 - the TCO frozen at submit time (plan §11.4). 404 if the
    proposal doesn't belong to this evaluation, or hasn't been submitted yet
    (no snapshot -> no tco_result to read, same "not available before
    submit" principle as scoring results)."""
    try:
        proposal = service.get_proposal(context.tenant_id, proposal_id)
    except ProposalNotFoundError:
        raise HTTPException(status_code=404) from None
    if proposal.evaluation_id != evaluation_id:
        raise HTTPException(status_code=404)
    current_snapshot = proposal.current_snapshot
    if current_snapshot is None or current_snapshot.tco_result is None:
        raise HTTPException(status_code=404)
    return _tco_result_response(current_snapshot.tco_result)
