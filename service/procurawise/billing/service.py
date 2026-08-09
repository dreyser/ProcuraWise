import logging
from datetime import UTC, datetime, timedelta

from pymongo.errors import DuplicateKeyError

from procurawise.audit.models import AuditAction
from procurawise.audit.service import AuditEventService
from procurawise.billing.exceptions import (
    EvaluationNotOwnedByTenantError,
    PurchaseAlreadyPaidError,
    PurchaseNotFoundError,
)
from procurawise.billing.models import (
    BillingAccount,
    CheckoutSessionRequest,
    PaymentWebhookEvent,
    Purchase,
    new_id,
)
from procurawise.billing.provider import PaymentProvider
from procurawise.billing.repository import (
    BillingAccountRepository,
    BillingWebhookEventRepository,
    PurchaseRepository,
)
from procurawise.evaluations.models import Evaluation
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.service import ActorNotFoundError, IdentityService
from procurawise.notifications.service import NotificationService
from procurawise.shared.context import ActorContext

logger = logging.getLogger("procurawise.billing")


class BillingService:
    """Fase 25 (billing/admin, ADR 0025, plan Bloqueante #1 Opcion A):
    one-time per-evaluation Checkout only. `create_checkout_session()` is
    called by the API router (real ActorContext available);
    `process_webhook_event()` is called by the real webhook route
    (no ActorContext - the audit actor is resolved from Purchase.
    initiated_by_membership_id, same pattern as notifications.service.
    NotificationService._record_delivery_audit). `apply_payment_completed()`
    is the single implementation of "what a completed payment does" - both
    the real webhook and the dev-only local simulator route call it
    directly, never two parallel implementations."""

    def __init__(
        self,
        purchases: PurchaseRepository,
        billing_accounts: BillingAccountRepository,
        webhook_events: BillingWebhookEventRepository,
        evaluations: EvaluationRepository,
        payment_provider: PaymentProvider,
        audit: AuditEventService,
        identity: IdentityService,
        notifications: NotificationService,
        *,
        stripe_price_id_evaluation: str,
        frontend_base_url: str,
        webhook_event_retention_days: int,
    ) -> None:
        self._purchases = purchases
        self._billing_accounts = billing_accounts
        self._webhook_events = webhook_events
        self._evaluations = evaluations
        self._payment_provider = payment_provider
        self._audit = audit
        self._identity = identity
        self._notifications = notifications
        self._price_id = stripe_price_id_evaluation
        self._frontend_base_url = frontend_base_url
        self._webhook_event_retention_days = webhook_event_retention_days

    # --- tenant-facing (real ActorContext) ---

    def create_checkout_session(
        self, tenant_id: str, evaluation_id: str, *, actor: ActorContext
    ) -> Purchase:
        evaluation_doc = self._evaluations.find_by_id(tenant_id, evaluation_id)
        if evaluation_doc is None:
            raise EvaluationNotOwnedByTenantError(evaluation_id)

        existing_doc = self._purchases.find_active_for_evaluation(tenant_id, evaluation_id)
        if existing_doc is not None:
            existing = Purchase.from_document(existing_doc)
            if existing.status == "paid":
                raise PurchaseAlreadyPaidError(evaluation_id)
            # status == "pending": reuse the still-open session rather than
            # create a second one (duplicate-click / double-charge hygiene).
            return existing

        account = self._get_or_create_billing_account(tenant_id)
        purchase_id = new_id()
        request = CheckoutSessionRequest(
            price_id=self._price_id,
            quantity=1,
            success_url=(
                f"{self._frontend_base_url}/billing/checkout/success?purchase_id={purchase_id}"
            ),
            cancel_url=f"{self._frontend_base_url}/billing/checkout/cancelled",
            idempotency_key=purchase_id,
            metadata={
                "tenant_id": tenant_id,
                "purchase_id": purchase_id,
                "evaluation_id": evaluation_id,
            },
            customer_id=account.stripe_customer_id,
        )
        handle = self._payment_provider.create_checkout_session(request)

        purchase = Purchase.create(
            id=purchase_id,
            tenant_id=tenant_id,
            evaluation_id=evaluation_id,
            initiated_by_membership_id=actor.membership_id,
            stripe_checkout_session_id=handle.session_id,
            stripe_price_id=self._price_id,
            checkout_url=handle.checkout_url,
        )
        self._purchases.insert(tenant_id, purchase.to_document())
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="billing_checkout_session_created",
            resource_type="purchase",
            resource_id=purchase.id,
            evaluation_id=evaluation_id,
            metadata={"stripe_checkout_session_id": purchase.stripe_checkout_session_id},
        )
        return purchase

    def get_purchase(self, tenant_id: str, purchase_id: str) -> Purchase:
        doc = self._purchases.find_by_id(tenant_id, purchase_id)
        if doc is None:
            raise PurchaseNotFoundError(purchase_id)
        return Purchase.from_document(doc)

    def list_purchases(self, tenant_id: str, *, evaluation_id: str | None = None) -> list[Purchase]:
        docs = self._purchases.list_for_tenant(tenant_id, evaluation_id=evaluation_id)
        return [Purchase.from_document(doc) for doc in docs]

    # --- webhook (no ActorContext) ---

    def process_webhook_event(self, raw_payload: bytes, signature_header: str) -> None:
        """Verification and idempotency both happen before any business
        logic runs - a replayed or duplicate-in-flight event_id short-
        circuits here via the ledger's unique _id, never reaching
        _dispatch_event a second time."""
        event = self._payment_provider.parse_webhook_event(raw_payload, signature_header)
        now = datetime.now(UTC)
        try:
            self._webhook_events.insert(
                {
                    "_id": event.event_id,
                    "event_type": event.event_type,
                    "received_at": now,
                    "processed_at": None,
                    "expires_at": now + timedelta(days=self._webhook_event_retention_days),
                }
            )
        except DuplicateKeyError:
            logger.info(
                "billing_webhook_event_already_processed", extra={"event_id": event.event_id}
            )
            return

        try:
            self._dispatch_event(event)
        except Exception:
            # Never leave a "claimed but never finished" ledger row behind -
            # Stripe's retry of the same event_id must be reprocessed
            # cleanly, not silently swallowed by a row that never completed.
            self._webhook_events.delete(event.event_id)
            raise
        self._webhook_events.mark_processed(event.event_id, datetime.now(UTC))

    def _dispatch_event(self, event: PaymentWebhookEvent) -> None:
        if event.event_type == "checkout.session.completed":
            self._handle_checkout_completed(event)
        elif event.event_type == "checkout.session.expired":
            self._handle_checkout_expired(event)
        else:
            logger.info(
                "billing_webhook_event_type_unhandled", extra={"event_type": event.event_type}
            )

    def _handle_checkout_completed(self, event: PaymentWebhookEvent) -> None:
        if event.payment_status != "paid":
            logger.info(
                "billing_webhook_checkout_completed_not_paid",
                extra={"session_id": event.session_id, "payment_status": event.payment_status},
            )
            return
        self.apply_payment_completed(
            event.session_id,
            payment_intent_id=event.payment_intent_id,
            amount_total=event.amount_total,
            currency=event.currency,
            expected_tenant_id=event.metadata.get("tenant_id"),
        )

    def _handle_checkout_expired(self, event: PaymentWebhookEvent) -> None:
        purchase_doc = self._purchases.find_by_stripe_session_id(event.session_id)
        if purchase_doc is None:
            logger.warning(
                "billing_webhook_unknown_session", extra={"session_id": event.session_id}
            )
            return
        purchase = Purchase.from_document(purchase_doc)
        now = datetime.now(UTC)
        transitioned = self._purchases.transition_status(
            purchase.tenant_id, purchase.id, "pending", "expired", {"updated_at": now}
        )
        if not transitioned:
            return
        self._record_audit(purchase.tenant_id, purchase, "billing_checkout_expired")

    # --- shared by the real webhook AND the dev-only local simulator ---

    def apply_payment_completed(
        self,
        stripe_checkout_session_id: str,
        *,
        payment_intent_id: str | None,
        amount_total: int | None,
        currency: str | None,
        expected_tenant_id: str | None = None,
    ) -> Purchase | None:
        """Returns the (possibly already-paid) Purchase when the session is
        known, so the dev-only local simulator route can build a redirect to
        the frontend success page - real Stripe webhook callers ignore the
        return value entirely."""
        purchase_doc = self._purchases.find_by_stripe_session_id(stripe_checkout_session_id)
        if purchase_doc is None:
            logger.warning(
                "billing_webhook_unknown_session",
                extra={"session_id": stripe_checkout_session_id},
            )
            return None
        purchase = Purchase.from_document(purchase_doc)
        # The tenant comes from our own row, never from the webhook payload's
        # metadata - this is only ever a cross-check that logs a discrepancy,
        # never the source of truth (plan S13.6).
        if expected_tenant_id is not None and expected_tenant_id != purchase.tenant_id:
            logger.warning(
                "billing_webhook_tenant_metadata_mismatch",
                extra={
                    "purchase_id": purchase.id,
                    "purchase_tenant_id": purchase.tenant_id,
                    "metadata_tenant_id": expected_tenant_id,
                },
            )

        now = datetime.now(UTC)
        transitioned = self._purchases.transition_status(
            purchase.tenant_id,
            purchase.id,
            "pending",
            "paid",
            {
                "paid_at": now,
                "updated_at": now,
                "stripe_payment_intent_id": payment_intent_id,
                "amount_total": amount_total,
                "currency": currency,
            },
        )
        paid_doc = self._purchases.find_by_id(purchase.tenant_id, purchase.id)
        assert paid_doc is not None
        paid_purchase = Purchase.from_document(paid_doc)
        if not transitioned:
            # Already "paid" (a second delivery that raced past the ledger's
            # own idempotency check) or already "expired" - either way, a
            # no-op is correct, never a second audit/notification.
            return paid_purchase

        self._record_audit(purchase.tenant_id, paid_purchase, "billing_payment_succeeded")
        self._notify_payment_succeeded(paid_purchase)
        return paid_purchase

    # --- helpers ---

    def _get_or_create_billing_account(self, tenant_id: str) -> BillingAccount:
        doc = self._billing_accounts.find_by_id(tenant_id)
        if doc is not None:
            return BillingAccount.from_document(doc)
        account = BillingAccount.create(tenant_id=tenant_id)
        try:
            self._billing_accounts.insert(tenant_id, account.to_document())
        except DuplicateKeyError:
            # Concurrent first-checkout race - the other request already
            # created it, same idempotent-insert idiom as Notification.
            doc = self._billing_accounts.find_by_id(tenant_id)
            assert doc is not None
            return BillingAccount.from_document(doc)
        return account

    def _record_audit(self, tenant_id: str, purchase: Purchase, action: AuditAction) -> None:
        """The worker/webhook has no HTTP-resolved ActorContext of its own -
        same pattern as notifications.service.NotificationService.
        _record_delivery_audit: resolve the Purchase's own initiator as the
        audit actor, and skip (best-effort) if that Membership no longer
        resolves."""
        try:
            actor = self._identity.resolve_actor_context(purchase.initiated_by_membership_id)
        except ActorNotFoundError:
            logger.warning(
                "billing_purchase_initiator_not_found_for_audit",
                extra={"purchase_id": purchase.id},
            )
            return
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            resource_type="purchase",
            resource_id=purchase.id,
            evaluation_id=purchase.evaluation_id,
            metadata={
                "stripe_checkout_session_id": purchase.stripe_checkout_session_id,
                "amount_total": purchase.amount_total,
                "currency": purchase.currency,
            },
        )

    def _notify_payment_succeeded(self, purchase: Purchase) -> None:
        evaluation_doc = self._evaluations.find_by_id(purchase.tenant_id, purchase.evaluation_id)
        evaluation_name = (
            Evaluation.from_document(evaluation_doc).name
            if evaluation_doc is not None
            else purchase.evaluation_id
        )
        self._notifications.notify(
            purchase.tenant_id,
            recipient_membership_id=purchase.initiated_by_membership_id,
            event="payment_succeeded",
            resource_type="purchase",
            resource_id=purchase.id,
            evaluation_id=purchase.evaluation_id,
            title="Pago confirmado",
            body=f'Tu pago para la evaluación "{evaluation_name}" fue confirmado exitosamente.',
        )
