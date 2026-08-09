"""Fase 25 (billing/admin, ADR 0025) - single composition point for
`BillingService`, shared by `billing.router`/`billing.webhook_router`
(FastAPI DI) and `procurawise.admin` (which needs its own PurchaseRepository
for the cross-tenant billing read) - same pattern as
`reports.dependencies.build_report_service`/
`notifications.dependencies.build_notification_service`."""

from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.service import AuditEventService
from procurawise.billing.provider import resolve_payment_provider
from procurawise.billing.repository import (
    BillingAccountRepository,
    BillingWebhookEventRepository,
    PurchaseRepository,
)
from procurawise.billing.service import BillingService
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.repository import (
    MembershipRepository,
    TenantRepository,
    UserRepository,
)
from procurawise.identity.service import IdentityService
from procurawise.notifications.dependencies import build_notification_service
from procurawise.shared.config import Settings
from procurawise.shared.mongo import get_database


def build_billing_service(settings: Settings) -> BillingService:
    db = get_database(settings)
    audit = AuditEventService(AuditEventRepository(db), settings)
    identity = IdentityService(
        tenants=TenantRepository(db),
        users=UserRepository(db),
        memberships=MembershipRepository(db),
    )
    return BillingService(
        purchases=PurchaseRepository(db),
        billing_accounts=BillingAccountRepository(db),
        webhook_events=BillingWebhookEventRepository(db),
        evaluations=EvaluationRepository(db),
        payment_provider=resolve_payment_provider(settings),
        audit=audit,
        identity=identity,
        notifications=build_notification_service(settings),
        stripe_price_id_evaluation=settings.stripe_price_id_evaluation or "",
        frontend_base_url=settings.frontend_base_url,
        webhook_event_retention_days=settings.billing_webhook_event_retention_days,
    )
