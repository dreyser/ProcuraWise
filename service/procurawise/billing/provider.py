import json
import logging
from typing import Protocol
from uuid import uuid4

from procurawise.billing.exceptions import InvalidWebhookSignatureError
from procurawise.billing.models import (
    CheckoutSessionHandle,
    CheckoutSessionRequest,
    PaymentWebhookEvent,
)
from procurawise.shared.config import Settings

logger = logging.getLogger("procurawise.billing.provider")

# The local/CI stand-in's fixed signature header value - LocalPaymentProvider
# accepts only this exact value, so a test can exercise "wrong signature"
# simply by sending anything else, without needing real HMAC machinery.
LOCAL_DEV_SIGNATURE_HEADER = "local-dev-signature"


class PaymentProvider(Protocol):
    """Vendor-neutral boundary for payment checkout (ADR 0025). Business
    services (`billing.service`) depend on this Protocol only, never on a
    concrete provider - same shape as `ai.provider.AIProvider`/
    `notifications.provider.NotificationEmailProvider`. Deliberately no
    `ping()` (unlike NotificationEmailProvider): Stripe must never be wired
    into `/health/ready` - an incident on Stripe's side must not take this
    service's own readiness probe down with it."""

    def create_checkout_session(self, request: CheckoutSessionRequest) -> CheckoutSessionHandle: ...

    def parse_webhook_event(self, payload: bytes, signature_header: str) -> PaymentWebhookEvent: ...


class LocalPaymentProvider:
    """Local/CI stand-in - no network, no Stripe SDK. Every unit/integration/
    E2E test and every `billing_enabled=False` environment (the default
    everywhere except production) runs against this. Session creation is
    answered instantly with a synthetic id pointing at the dev-only
    `GET /billing/local-checkout/{session_id}` simulator route
    (billing/router.py), which drives the exact same
    BillingService.apply_payment_completed() the real webhook handler calls
    - never a second, parallel implementation of "what a completed payment
    does"."""

    def create_checkout_session(self, request: CheckoutSessionRequest) -> CheckoutSessionHandle:
        session_id = f"cs_local_{uuid4().hex}"
        return CheckoutSessionHandle(
            session_id=session_id,
            checkout_url=f"/api/v1/billing/local-checkout/{session_id}",
        )

    def parse_webhook_event(self, payload: bytes, signature_header: str) -> PaymentWebhookEvent:
        if signature_header != LOCAL_DEV_SIGNATURE_HEADER:
            raise InvalidWebhookSignatureError()
        data = json.loads(payload)
        return PaymentWebhookEvent(
            event_id=data["event_id"],
            event_type=data["event_type"],
            session_id=data["session_id"],
            payment_status=data["payment_status"],
            amount_total=data.get("amount_total"),
            currency=data.get("currency"),
            payment_intent_id=data.get("payment_intent_id"),
            metadata=data.get("metadata", {}),
        )


def resolve_payment_provider(settings: Settings) -> PaymentProvider:
    """Single point both `billing.dependencies.build_billing_service` and
    (once it exists) any other composition site call - avoids each hand-
    rolling its own try/except around StripePaymentProvider.from_settings()."""
    if not settings.billing_enabled:
        return LocalPaymentProvider()

    # Imported here, not at module level: stripe_payment_provider imports the
    # `stripe` SDK, and this module (billing.provider) is the Protocol every
    # provider is defined against, so it must not itself depend on the one
    # concrete implementation (ADR 0025, CLAUDE.md S5.1).
    from procurawise.billing.stripe_payment_provider import StripePaymentProvider

    try:
        return StripePaymentProvider.from_settings(settings)
    except ValueError:
        logger.warning(
            "stripe_not_configured - falling back to LocalPaymentProvider "
            "(billing_enabled=true requires stripe_secret_key/stripe_webhook_secret/"
            "stripe_price_id_evaluation)"
        )
        return LocalPaymentProvider()
