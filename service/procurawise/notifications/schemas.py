from datetime import datetime

from procurawise.notifications.models import NotificationEvent
from procurawise.shared.api_models import APIModel


class NotificationResponse(APIModel):
    id: str
    event: NotificationEvent
    resource_type: str
    resource_id: str
    evaluation_id: str | None
    title: str
    body: str
    created_at: datetime
    read_at: datetime | None


class NotificationListResponse(APIModel):
    items: list[NotificationResponse]
    unread_count: int
