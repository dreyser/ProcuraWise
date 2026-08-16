import stripe
from stripe.params.checkout import SessionCreateParams

from procurawise.billing.exceptions import InvalidWebhookSignatureError
from procurawise.billing.models import (
    CheckoutSessionHandle,
    CheckoutSessionRequest,
    PaymentWebhookEvent,
)
from procurawise.shared.config import Settings


class StripePaymentProvider:
    """The only file in this codebase authorized to import the `stripe` SDK
    (ADR 0025) - same import-boundary discipline CLAUDE.md S5.1 already
    applies to `ai/azure_openai_provider.py` and
    `notifications/azure_acs_email_provider.py`, extended here to a third
    external SDK family. Uses a `stripe.StripeClient` bound to its own
    `api_key`/`http_client` per instance (never `stripe.api_key`/
    `stripe.default_http_client` module-level state), so multiple instances
    (e.g. under test, each with a different timeout) never race on shared
    global state."""

    def __init__(self, *, api_key: str, webhook_secret: str, timeout_seconds: int) -> None:
        self._webhook_secret = webhook_secret
        self._timeout_seconds = timeout_seconds
        self._client = stripe.StripeClient(
            api_key=api_key,
            http_client=stripe.RequestsClient(timeout=timeout_seconds),
        )

    @staticmethod
    def from_settings(settings: Settings) -> "StripePaymentProvider":
        if not (
            settings.stripe_secret_key
            and settings.stripe_webhook_secret
            and settings.stripe_price_id_evaluation
        ):
            raise ValueError(
                "incomplete Stripe configuration - stripe_secret_key/stripe_webhook_secret/"
                "stripe_price_id_evaluation are all required"
            )
        return StripePaymentProvider(
            api_key=settings.stripe_secret_key,
            webhook_secret=settings.stripe_webhook_secret,
            timeout_seconds=settings.stripe_request_timeout_seconds,
        )

    def create_checkout_session(self, request: CheckoutSessionRequest) -> CheckoutSessionHandle:
        # mode="payment" (plan Bloqueante #1 Opcion A) - never "subscription".
        # Never an `amount`/`currency` here: `price` is the only value that
        # determines cost, and it is always resolved server-side from
        # configuration (billing/service.py), never accepted from a client.
        params: SessionCreateParams = {
            "mode": "payment",
            "line_items": [{"price": request.price_id, "quantity": request.quantity}],
            "payment_method_types": ["card"],
            "success_url": request.success_url,
            "cancel_url": request.cancel_url,
            "metadata": request.metadata,
        }
        if request.customer_id:
            params["customer"] = request.customer_id
        # `timeout` is deliberately never a key in `params`/`options` here -
        # the installed stripe SDK (15.4.0) has no per-call timeout override;
        # it serializes any unrecognized key straight into the Checkout
        # Session API body, which Stripe rejects ("Received unknown
        # parameter: timeout"). The transport timeout is instead bound once,
        # per-instance, into `self._client`'s `RequestsClient` above.
        session = self._client.v1.checkout.sessions.create(
            params=params,
            options={"idempotency_key": request.idempotency_key},
        )
        if session.url is None:
            # Stripe's own type contract allows this only for a Session that
            # never reached a state with a hosted page - never observed for
            # mode="payment" with line_items in practice, but the SDK types
            # it as optional, so this boundary is validated rather than
            # asserted away.
            raise ValueError(f"Stripe returned no checkout URL for session {session.id}")
        return CheckoutSessionHandle(session_id=session.id, checkout_url=session.url)

    def parse_webhook_event(self, payload: bytes, signature_header: str) -> PaymentWebhookEvent:
        try:
            event = stripe.Webhook.construct_event(payload, signature_header, self._webhook_secret)
        except Exception as exc:  # noqa: BLE001 - any signature/timestamp/parse failure must
            # become a 400 here (billing/webhook_router.py), never bubble up as an unhandled
            # 500 with an SDK-internal stack trace this module doesn't need to enumerate.
            raise InvalidWebhookSignatureError() from exc

        # `event["data"]["object"]` is a StripeObject, not a dict - it
        # supports `[...]` (via __getitem__) but not `.get(...)` (its
        # __getattr__ shadows a real "get" field name, so `.get` raises
        # AttributeError instead of returning the bound dict method).
        # `.to_dict()` gives back a plain dict so `.get(...)` behaves as
        # expected for every optional field below.
        session = event["data"]["object"].to_dict()
        return PaymentWebhookEvent(
            event_id=event["id"],
            event_type=event["type"],
            session_id=session.get("id", ""),
            payment_status=session.get("payment_status", ""),
            amount_total=session.get("amount_total"),
            currency=session.get("currency"),
            payment_intent_id=session.get("payment_intent"),
            metadata=dict(session.get("metadata") or {}),
        )
