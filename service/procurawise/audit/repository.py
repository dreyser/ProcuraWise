from datetime import datetime
from typing import Any

from pymongo.database import Database

from procurawise.shared.tenant_collection import TenantCollection

AuditEventCursor = tuple[datetime, str]  # (occurred_at, id) - see plan §8/§11


class AuditEventRepository:
    """Deliberately exposes only `record` (insert) and read methods - never
    `update`/`delete`/`replace`. This is the append-only guarantee (plan §8):
    no code path in this class can mutate or remove a persisted AuditEvent,
    and no other module may reach around it (TenantCollection itself is never
    exposed, only used internally here)."""

    def __init__(self, db: Database) -> None:
        self._collection = db["audit_events"]

    def _scoped(self, tenant_id: str) -> TenantCollection:
        return TenantCollection(self._collection, tenant_id)

    def record(self, tenant_id: str, document: dict[str, Any]) -> None:
        self._scoped(tenant_id).insert_one(document)

    def list_for_evaluation(
        self,
        tenant_id: str,
        evaluation_id: str,
        *,
        limit: int,
        cursor: AuditEventCursor | None,
    ) -> list[dict[str, Any]]:
        """Stable-order (occurred_at desc, id desc) page. Fetches `limit + 1`
        so the caller can tell whether a next page exists without a second
        query - same pattern as identity.repository.VendorOrganizationRepository."""
        filter_: dict[str, Any] = {"evaluation_id": evaluation_id}
        if cursor is not None:
            cursor_occurred_at, cursor_id = cursor
            filter_["$or"] = [
                {"occurred_at": {"$lt": cursor_occurred_at}},
                {"occurred_at": cursor_occurred_at, "_id": {"$lt": cursor_id}},
            ]
        results = (
            self._scoped(tenant_id)
            .find(filter_)
            .sort([("occurred_at", -1), ("_id", -1)])
            .limit(limit + 1)
        )
        return list(results)
