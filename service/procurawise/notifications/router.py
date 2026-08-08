from fastapi import APIRouter, Depends, HTTPException

from procurawise.notifications.dependencies import build_notification_service
from procurawise.notifications.exceptions import NotificationNotFoundError
from procurawise.notifications.models import Notification
from procurawise.notifications.schemas import NotificationListResponse, NotificationResponse
from procurawise.notifications.service import NotificationService
from procurawise.shared.api_models import APIModel
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext, require_role
from procurawise.shared.roles import BUYER_LOGIN_ROLES
from procurawise.vendor_portal.dependencies import require_vendor_context

buyer_notifications_router = APIRouter(prefix="/notifications", tags=["notifications"])
vendor_notifications_router = APIRouter(
    prefix="/vendor-portal/notifications", tags=["vendor-portal-notifications"]
)

# Every buyer role that can authenticate at all may be a notification
# recipient (spec S11's destinatarios span owner/evaluator/approver/internal
# collaborator) - authorization narrows to "this exact recipient" inside the
# service layer (NotificationRepository.mark_read/list_for_recipient always
# filter by the resolved actor's own membership_id, never a role tuple),
# same identity-based-not-role-based boundary the plan calls for.
require_buyer_notifications_reader = require_role(*BUYER_LOGIN_ROLES)


class MarkAllReadResponse(APIModel):
    marked_count: int


def get_notification_service(
    settings: Settings = Depends(get_settings),
) -> NotificationService:
    return build_notification_service(settings)


def _response(notification: Notification) -> NotificationResponse:
    return NotificationResponse(
        id=notification.id,
        event=notification.event,
        resource_type=notification.resource_type,
        resource_id=notification.resource_id,
        evaluation_id=notification.evaluation_id,
        title=notification.title,
        body=notification.body,
        created_at=notification.created_at,
        read_at=notification.read_at,
    )


@buyer_notifications_router.get("", response_model=NotificationListResponse)
def list_notifications_as_buyer(
    context: ActorContext = Depends(require_buyer_notifications_reader),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationListResponse:
    items, unread_count = service.list_for_recipient(
        context.tenant_id, recipient_membership_id=context.membership_id
    )
    return NotificationListResponse(items=[_response(n) for n in items], unread_count=unread_count)


@buyer_notifications_router.patch("/read-all", response_model=MarkAllReadResponse)
def mark_all_read_as_buyer(
    context: ActorContext = Depends(require_buyer_notifications_reader),
    service: NotificationService = Depends(get_notification_service),
) -> MarkAllReadResponse:
    count = service.mark_all_read(context.tenant_id, recipient_membership_id=context.membership_id)
    return MarkAllReadResponse(marked_count=count)


@buyer_notifications_router.patch("/{notification_id}/read", status_code=204)
def mark_read_as_buyer(
    notification_id: str,
    context: ActorContext = Depends(require_buyer_notifications_reader),
    service: NotificationService = Depends(get_notification_service),
) -> None:
    try:
        service.mark_read(
            context.tenant_id,
            notification_id,
            recipient_membership_id=context.membership_id,
        )
    except NotificationNotFoundError:
        raise HTTPException(status_code=404) from None


@vendor_notifications_router.get("", response_model=NotificationListResponse)
def list_notifications_as_vendor(
    context: ActorContext = Depends(require_vendor_context),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationListResponse:
    items, unread_count = service.list_for_recipient(
        context.tenant_id, recipient_membership_id=context.membership_id
    )
    return NotificationListResponse(items=[_response(n) for n in items], unread_count=unread_count)


@vendor_notifications_router.patch("/read-all", response_model=MarkAllReadResponse)
def mark_all_read_as_vendor(
    context: ActorContext = Depends(require_vendor_context),
    service: NotificationService = Depends(get_notification_service),
) -> MarkAllReadResponse:
    count = service.mark_all_read(context.tenant_id, recipient_membership_id=context.membership_id)
    return MarkAllReadResponse(marked_count=count)


@vendor_notifications_router.patch("/{notification_id}/read", status_code=204)
def mark_read_as_vendor(
    notification_id: str,
    context: ActorContext = Depends(require_vendor_context),
    service: NotificationService = Depends(get_notification_service),
) -> None:
    try:
        service.mark_read(
            context.tenant_id,
            notification_id,
            recipient_membership_id=context.membership_id,
        )
    except NotificationNotFoundError:
        raise HTTPException(status_code=404) from None
