from fastapi import APIRouter, Depends, Request

from procurawise.agreements import legal_content
from procurawise.agreements.schemas import AgreementAcceptRequest, AgreementStatusResponse
from procurawise.agreements.service import AgreementService
from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.service import AuditEventService
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext
from procurawise.shared.mongo import get_database
from procurawise.shared.request_ip import resolve_client_ip
from procurawise.vendor_portal.dependencies import get_agreement_service, require_vendor_context

# Deliberately not gated by require_agreements_accepted (vendor_portal
# dependencies.py) - a vendor must be able to see and accept the Agreement
# gate before it can ever be enforced against them, or no one could clear
# it. require_vendor_context alone (real vendor JWT + role + vendor_org_id
# present) is the correct, narrower gate for these two endpoints.
router = APIRouter(prefix="/vendor-portal/agreements", tags=["vendor-portal"])


@router.get("/status", response_model=AgreementStatusResponse)
def get_agreement_status(
    context: ActorContext = Depends(require_vendor_context),
    agreements: AgreementService = Depends(get_agreement_service),
) -> AgreementStatusResponse:
    return AgreementStatusResponse(
        nda_accepted=agreements.has_current_acceptance(context.tenant_id, context.user_id, "nda"),
        conflict_of_interest_accepted=agreements.has_current_acceptance(
            context.tenant_id, context.user_id, "conflict_of_interest"
        ),
        current_nda_version=legal_content.current_version("nda"),
        current_conflict_of_interest_version=legal_content.current_version("conflict_of_interest"),
        nda_text=legal_content.text_for("nda"),
        conflict_of_interest_text=legal_content.text_for("conflict_of_interest"),
    )


@router.post("/accept", response_model=AgreementStatusResponse)
def accept_agreement(
    body: AgreementAcceptRequest,
    request: Request,
    context: ActorContext = Depends(require_vendor_context),
    agreements: AgreementService = Depends(get_agreement_service),
    settings: Settings = Depends(get_settings),
) -> AgreementStatusResponse:
    agreements.accept(
        context.tenant_id,
        context.user_id,
        context.membership_id,
        body.type,
        ip=resolve_client_ip(request, settings),
        user_agent=request.headers.get("user-agent"),
    )
    db = get_database(settings)
    AuditEventService(AuditEventRepository(db), settings).record(
        tenant_id=context.tenant_id,
        actor=context,
        action="agreement_accepted",
        resource_type="vendor_organization",
        resource_id=context.vendor_org_id or context.membership_id,
        metadata={"type": body.type},
    )
    return get_agreement_status(context=context, agreements=agreements)
