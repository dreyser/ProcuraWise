from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4


def new_id() -> str:
    return uuid4().hex


# Fase 25 (billing/admin, ADR 0025, plan Bloqueante #1 Opcion A): one-time
# per-evaluation Checkout only - no subscription lifecycle in this phase.
# "pending" covers both "just created" and "Checkout Session still open in
# Stripe's hosted page"; "paid"/"expired" are both terminal - a new attempt
# always creates a new Purchase, never reopens one of these.
PurchaseStatus = Literal["pending", "paid", "expired"]


@dataclass(frozen=True)
class Purchase:
    """Grain: one document per checkout attempt (tenant-scoped, collection
    `purchases`) - not one per evaluation, since a expired attempt followed
    by a real one must not collide. `stripe_checkout_session_id` (unique
    index) is the sole join key the webhook uses to find this row; the
    tenant comes from this row, never from the webhook payload's own
    metadata (see billing/service.py). `amount_total`/`currency`/
    `stripe_payment_intent_id` are deliberately None until the webhook
    confirms completion - this dataclass never carries a client-supplied or
    speculative amount, only what Stripe itself later reports back."""

    id: str
    tenant_id: str
    evaluation_id: str
    initiated_by_membership_id: str
    status: PurchaseStatus
    stripe_checkout_session_id: str
    stripe_price_id: str
    # Stored at creation, not reconstructed later: unlike LocalPaymentProvider
    # (whose URL is deterministic from session_id), Stripe's real hosted
    # Checkout URL is an opaque, non-deterministic value - re-deriving it
    # would need a second provider call every time a pending Purchase is
    # reused (billing/service.py's "same evaluation, still pending" rule).
    checkout_url: str
    stripe_payment_intent_id: str | None
    amount_total: int | None
    currency: str | None
    created_at: datetime
    updated_at: datetime
    paid_at: datetime | None

    @staticmethod
    def create(
        *,
        id: str,
        tenant_id: str,
        evaluation_id: str,
        initiated_by_membership_id: str,
        stripe_checkout_session_id: str,
        stripe_price_id: str,
        checkout_url: str,
    ) -> "Purchase":
        """`id` is supplied by the caller (billing/service.py, via
        billing.models.new_id()), not generated here - unlike every other
        create() factory in this codebase, the caller needs the Purchase's
        own id *before* this object can be fully constructed, to hand to
        Stripe as the idempotency_key and success/cancel-url purchase_id
        before the checkout_url it returns is even known."""
        now = datetime.now(UTC)
        return Purchase(
            id=id,
            tenant_id=tenant_id,
            evaluation_id=evaluation_id,
            initiated_by_membership_id=initiated_by_membership_id,
            status="pending",
            stripe_checkout_session_id=stripe_checkout_session_id,
            stripe_price_id=stripe_price_id,
            checkout_url=checkout_url,
            stripe_payment_intent_id=None,
            amount_total=None,
            currency=None,
            created_at=now,
            updated_at=now,
            paid_at=None,
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "tenant_id": self.tenant_id,
            "evaluation_id": self.evaluation_id,
            "initiated_by_membership_id": self.initiated_by_membership_id,
            "status": self.status,
            "stripe_checkout_session_id": self.stripe_checkout_session_id,
            "stripe_price_id": self.stripe_price_id,
            "checkout_url": self.checkout_url,
            "stripe_payment_intent_id": self.stripe_payment_intent_id,
            "amount_total": self.amount_total,
            "currency": self.currency,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "paid_at": self.paid_at,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "Purchase":
        return Purchase(
            id=doc["_id"],
            tenant_id=doc["tenant_id"],
            evaluation_id=doc["evaluation_id"],
            initiated_by_membership_id=doc["initiated_by_membership_id"],
            status=doc["status"],
            stripe_checkout_session_id=doc["stripe_checkout_session_id"],
            stripe_price_id=doc["stripe_price_id"],
            checkout_url=doc["checkout_url"],
            stripe_payment_intent_id=doc.get("stripe_payment_intent_id"),
            amount_total=doc.get("amount_total"),
            currency=doc.get("currency"),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
            paid_at=doc.get("paid_at"),
        )


@dataclass(frozen=True)
class BillingAccount:
    """Grain: one per tenant (`id == tenant_id`, same deterministic-id
    precedent as `EvaluationSnapshot.snapshot_id == evaluation_id`) - a thin
    anchor for `stripe_customer_id` only. Deliberately carries no `plan`/
    `limits`/`status` field: the commercial model beyond one-time
    per-evaluation purchase is undecided (plan Bloqueante #1), and inventing
    those fields now would be exactly the kind of unrequested scope
    CLAUDE.md S8 forbids. Created lazily on first checkout
    (billing/service.py), not sembrado in bulk."""

    tenant_id: str
    stripe_customer_id: str | None
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def create(tenant_id: str) -> "BillingAccount":
        now = datetime.now(UTC)
        return BillingAccount(
            tenant_id=tenant_id, stripe_customer_id=None, created_at=now, updated_at=now
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.tenant_id,
            "tenant_id": self.tenant_id,
            "stripe_customer_id": self.stripe_customer_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "BillingAccount":
        return BillingAccount(
            tenant_id=doc["tenant_id"],
            stripe_customer_id=doc.get("stripe_customer_id"),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )


# --- Provider-independent payment boundary (billing/provider.py) ---
# Same shape as ai.models.AIRequest/AIResponse and notifications.models.
# EmailMessage - no concrete Stripe object ever crosses this boundary.


@dataclass(frozen=True)
class CheckoutSessionRequest:
    price_id: str
    quantity: int
    success_url: str
    cancel_url: str
    idempotency_key: str
    metadata: dict[str, str]
    customer_id: str | None


@dataclass(frozen=True)
class CheckoutSessionHandle:
    session_id: str
    checkout_url: str


@dataclass(frozen=True)
class PaymentWebhookEvent:
    """Parsed, verified payload - never a raw stripe.Event/stripe.checkout.
    Session object. `payment_status` mirrors Stripe's own Checkout Session
    field ("paid"/"unpaid"/"no_payment_required")."""

    event_id: str
    event_type: str
    session_id: str
    payment_status: str
    amount_total: int | None
    currency: str | None
    payment_intent_id: str | None
    metadata: dict[str, str]
