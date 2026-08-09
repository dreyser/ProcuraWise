from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse

from procurawise.billing.dependencies import build_billing_service
from procurawise.billing.exceptions import (
    EvaluationNotOwnedByTenantError,
    PurchaseAlreadyPaidError,
    PurchaseNotFoundError,
)
from procurawise.billing.models import Purchase
from procurawise.billing.schemas import (
    CreateCheckoutSessionRequest,
    PurchaseListResponse,
    PurchaseResponse,
)
from procurawise.billing.service import BillingService
from procurawise.identity.dev_provider import require_dev_environment
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext, require_role
from procurawise.shared.roles import BILLING_READ_ROLES, BILLING_WRITE_ROLES

router = APIRouter(prefix="/billing", tags=["billing"])

require_billing_write = require_role(*BILLING_WRITE_ROLES)
require_billing_read = require_role(*BILLING_READ_ROLES)


def get_billing_service(settings: Settings = Depends(get_settings)) -> BillingService:
    return build_billing_service(settings)


def _purchase_response(purchase: Purchase) -> PurchaseResponse:
    return PurchaseResponse(
        id=purchase.id,
        evaluation_id=purchase.evaluation_id,
        status=purchase.status,
        checkout_url=purchase.checkout_url,
        amount_total=purchase.amount_total,
        currency=purchase.currency,
        created_at=purchase.created_at,
        paid_at=purchase.paid_at,
    )


@router.post("/checkout-sessions", response_model=PurchaseResponse, status_code=201)
def create_checkout_session(
    body: CreateCheckoutSessionRequest,
    context: ActorContext = Depends(require_billing_write),
    service: BillingService = Depends(get_billing_service),
) -> PurchaseResponse:
    try:
        purchase = service.create_checkout_session(
            context.tenant_id, body.evaluation_id, actor=context
        )
    except EvaluationNotOwnedByTenantError:
        raise HTTPException(status_code=404) from None
    except PurchaseAlreadyPaidError:
        raise HTTPException(status_code=409, detail="evaluation already paid") from None
    return _purchase_response(purchase)


@router.get("/purchases", response_model=PurchaseListResponse)
def list_purchases(
    evaluation_id: str | None = None,
    context: ActorContext = Depends(require_billing_read),
    service: BillingService = Depends(get_billing_service),
) -> PurchaseListResponse:
    purchases = service.list_purchases(context.tenant_id, evaluation_id=evaluation_id)
    return PurchaseListResponse(items=[_purchase_response(p) for p in purchases])


@router.get("/purchases/{purchase_id}", response_model=PurchaseResponse)
def get_purchase(
    purchase_id: str,
    context: ActorContext = Depends(require_billing_read),
    service: BillingService = Depends(get_billing_service),
) -> PurchaseResponse:
    try:
        purchase = service.get_purchase(context.tenant_id, purchase_id)
    except PurchaseNotFoundError:
        raise HTTPException(status_code=404) from None
    return _purchase_response(purchase)


# Dev-only local Checkout simulator (LocalPaymentProvider's checkout_url
# points here) - stands in for Stripe's hosted page so the full flow is
# demoable/E2E-testable with zero network. Drives the exact same
# BillingService.apply_payment_completed() the real webhook handler calls,
# never a second parallel implementation of "what a completed payment does".
@router.get("/local-checkout/{session_id}", include_in_schema=False)
def local_checkout_simulator(
    session_id: str,
    settings: Settings = Depends(get_settings),
    service: BillingService = Depends(get_billing_service),
) -> RedirectResponse:
    require_dev_environment(settings)
    purchase = service.apply_payment_completed(
        session_id,
        payment_intent_id=f"pi_local_{session_id}",
        amount_total=15000000,
        currency="mxn",
    )
    if purchase is None:
        raise HTTPException(status_code=404)
    return RedirectResponse(
        f"{settings.frontend_base_url}/billing/checkout/success?purchase_id={purchase.id}"
    )
