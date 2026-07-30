from datetime import datetime
from typing import Any

from procurawise.shared.api_models import APIModel


class AuditEventResponse(APIModel):
    id: str
    occurred_at: datetime
    actor_type: str
    actor_membership_id: str
    actor_user_id: str | None = None
    actor_vendor_org_id: str | None = None
    actor_role: str
    action: str
    resource_type: str
    resource_id: str
    evaluation_id: str | None = None
    proposal_id: str | None = None
    snapshot_id: str | None = None
    version: int | None = None
    outcome: str
    correlation_id: str | None = None
    metadata: dict[str, Any]


class AuditEventListResponse(APIModel):
    items: list[AuditEventResponse]
    next_cursor: str | None = None
