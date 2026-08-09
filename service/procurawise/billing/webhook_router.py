from fastapi import APIRouter, Depends, HTTPException, Request

from procurawise.billing.dependencies import build_billing_service
from procurawise.billing.exceptions import InvalidWebhookSignatureError
from procurawise.billing.service import BillingService
from procurawise.shared.config import Settings, get_settings

# Physically separate from billing/router.py (never mixed with the
# tenant-facing, JWT-gated endpoints there) - a Stripe webhook arrives
# server-to-server with no user JWT of any kind. The signature header IS the
# authentication; no `Depends(require_role(...))` of any kind is attached to
# this route.
router = APIRouter(prefix="/billing", tags=["billing-webhook"])


def get_billing_service(settings: Settings = Depends(get_settings)) -> BillingService:
    return build_billing_service(settings)


@router.post("/stripe/webhook", include_in_schema=False, status_code=200)
async def stripe_webhook(
    request: Request,
    service: BillingService = Depends(get_billing_service),
) -> dict[str, str]:
    # Raw body, never a Pydantic model - a model would re-serialize the
    # payload and break HMAC signature verification, which is computed over
    # the exact bytes Stripe sent.
    raw_payload = await request.body()
    signature_header = request.headers.get("Stripe-Signature", "")
    try:
        service.process_webhook_event(raw_payload, signature_header)
    except InvalidWebhookSignatureError:
        raise HTTPException(status_code=400, detail="invalid signature") from None
    return {"status": "ok"}
