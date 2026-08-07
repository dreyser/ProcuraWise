"""Fase 24 - single composition point for `NotificationService`, shared by
`notifications.router` (FastAPI DI) and `worker.main` (plain function call,
no FastAPI request scope) so the two never drift out of sync with each
other - same pattern as `reports.dependencies.build_report_service`."""

from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.service import AuditEventService
from procurawise.identity.repository import (
    MembershipRepository,
    TenantRepository,
    UserRepository,
)
from procurawise.identity.service import IdentityService
from procurawise.notifications.provider import resolve_notification_email_provider
from procurawise.notifications.repository import NotificationRepository
from procurawise.notifications.service import NotificationService
from procurawise.shared.config import Settings
from procurawise.shared.messaging import get_message_bus
from procurawise.shared.mongo import get_database


def build_notification_service(settings: Settings) -> NotificationService:
    db = get_database(settings)
    audit = AuditEventService(AuditEventRepository(db), settings)
    identity = IdentityService(
        tenants=TenantRepository(db),
        users=UserRepository(db),
        memberships=MembershipRepository(db),
    )
    return NotificationService(
        notifications=NotificationRepository(db),
        email_provider=resolve_notification_email_provider(settings),
        message_bus=get_message_bus(settings),
        audit=audit,
        identity=identity,
        retention_days=settings.notification_retention_days,
        max_attempts=settings.notification_email_max_attempts,
        retry_delay_minutes_1=settings.notification_email_retry_delay_minutes_1,
        retry_delay_minutes_2=settings.notification_email_retry_delay_minutes_2,
    )
