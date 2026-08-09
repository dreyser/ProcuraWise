from datetime import datetime

from procurawise.billing.models import PurchaseStatus
from procurawise.shared.api_models import APIModel


class CreateCheckoutSessionRequest(APIModel):
    """Deliberately only `evaluation_id` - `extra="forbid"` (APIModel) turns
    any client-sent `amount`/`price_id`/`currency`/`tenant_id` into a 422.
    The Price is always resolved server-side from configuration
    (billing/service.py), never accepted from a client."""

    evaluation_id: str


class PurchaseResponse(APIModel):
    id: str
    evaluation_id: str
    status: PurchaseStatus
    checkout_url: str
    amount_total: int | None
    currency: str | None
    created_at: datetime
    paid_at: datetime | None


class PurchaseListResponse(APIModel):
    items: list[PurchaseResponse]
