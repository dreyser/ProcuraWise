from fastapi import Depends, HTTPException

from procurawise.agreements.repository import AgreementRepository
from procurawise.agreements.service import AgreementService
from procurawise.identity.jwt_provider import get_current_vendor_context
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext
from procurawise.shared.mongo import get_database


# Fase 15: production identity for vendor_portal is a real vendor JWT
# (token_use=vendor_access), same as AUTH-PROD already did for buyer routes
# - the interim identity.dev_provider.get_current_context mechanism is no
# longer accepted here (a request carrying only X-Dev-Membership-Id now 401s
# on every vendor_portal route, mirroring exactly what already happened to
# buyer routes). The dev-header mechanism itself is not deleted: /dev/actors
# and /me still serve local/test tooling unchanged.
#
# Deliberately NOT shared.context.require_role: vendor_portal keeps its own
# dependency, anchored directly to identity.jwt_provider, so a future change
# to require_role (buyer-only by convention) can never accidentally widen or
# narrow vendor access as a side effect - same isolation rationale the
# previous (dev-header) version of this function already documented.
def require_vendor_role(
    context: ActorContext = Depends(get_current_vendor_context),
) -> ActorContext:
    if context.role != "vendor_contact":
        raise HTTPException(status_code=403, detail="role not permitted")
    return context


def require_vendor_context(
    context: ActorContext = Depends(require_vendor_role),
) -> ActorContext:
    # Membership.create already forbids a vendor_contact row without
    # vendor_org_id, but this is the boundary where an untrusted request
    # meets that invariant - fail closed rather than trust it silently.
    if context.vendor_org_id is None:
        raise HTTPException(status_code=403)
    return context


def get_agreement_service(settings: Settings = Depends(get_settings)) -> AgreementService:
    db = get_database(settings)
    return AgreementService(AgreementRepository(db))


def require_agreements_accepted(
    context: ActorContext = Depends(require_vendor_context),
    agreements: AgreementService = Depends(get_agreement_service),
) -> ActorContext:
    """Fase 15 backlog acceptance criterion: "Proveedor no accede al
    formulario de respuesta sin aceptar ambos Agreement". Applied to every
    vendor_portal/proposals endpoint except the agreements status/accept
    endpoints themselves (vendor_portal/agreements_router.py) - a vendor
    must be able to see and accept the Agreement gate before it can be
    enforced against them, or no one could ever clear it."""
    missing = agreements.missing_agreement_types(context.tenant_id, context.user_id)
    if missing:
        raise HTTPException(
            status_code=403,
            detail={"detail": "agreements_required", "missing": missing},
        )
    return context
