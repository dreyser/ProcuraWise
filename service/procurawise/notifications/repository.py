from datetime import datetime
from typing import Any

from pymongo.database import Database

from procurawise.shared.tenant_collection import TenantCollection


class NotificationRepository:
    def __init__(self, db: Database) -> None:
        self._collection = db["notifications"]

    def _scoped(self, tenant_id: str) -> TenantCollection:
        return TenantCollection(self._collection, tenant_id)

    def insert(self, tenant_id: str, document: dict[str, Any]) -> None:
        self._scoped(tenant_id).insert_one(document)

    def find_by_id(self, tenant_id: str, notification_id: str) -> dict[str, Any] | None:
        return self._scoped(tenant_id).find_one({"_id": notification_id})

    def list_for_recipient(
        self, tenant_id: str, recipient_membership_id: str, *, limit: int
    ) -> list[dict[str, Any]]:
        return list(
            self._scoped(tenant_id)
            .find({"recipient_membership_id": recipient_membership_id})
            .sort("created_at", -1)
            .limit(limit)
        )

    def count_unread(self, tenant_id: str, recipient_membership_id: str) -> int:
        return self._scoped(tenant_id).count_documents(
            {"recipient_membership_id": recipient_membership_id, "read_at": None}
        )

    def mark_read(
        self,
        tenant_id: str,
        notification_id: str,
        recipient_membership_id: str,
        read_at: datetime,
    ) -> bool:
        """Filter includes recipient_membership_id, not just _id - this is
        where the identity-based authorization boundary actually lives
        (notifications/service.py never trusts a caller-supplied
        membership_id either way): a membership can never mark another
        recipient's Notification as read, even within the same tenant."""
        result = self._scoped(tenant_id).update_one(
            {"_id": notification_id, "recipient_membership_id": recipient_membership_id},
            {"$set": {"read_at": read_at}},
        )
        return result.matched_count > 0

    def mark_all_read(self, tenant_id: str, recipient_membership_id: str, read_at: datetime) -> int:
        result = self._scoped(tenant_id).update_many(
            {"recipient_membership_id": recipient_membership_id, "read_at": None},
            {"$set": {"read_at": read_at}},
        )
        return result.modified_count

    # --- email delivery/retry (worker-side only) ---

    def transition_email_status(
        self,
        tenant_id: str,
        notification_id: str,
        from_status: str,
        to_status: str,
        extra_set: dict[str, Any] | None = None,
    ) -> bool:
        """Same atomic, status-conditioned transition pattern as
        ReportRepository.transition_status - the filter's email_status
        clause is the concurrency control."""
        update = dict(extra_set or {})
        update["email_status"] = to_status
        result = self._scoped(tenant_id).update_one(
            {"_id": notification_id, "email_status": from_status},
            {"$set": update},
        )
        return result.matched_count > 0

    def find_due_email_retries(self, *, before: datetime, limit: int) -> list[dict[str, Any]]:
        """Cross-tenant, worker-only sweep backing shared.worker_loop's
        time_based_tasks - deliberately bypasses TenantCollection (must scan
        every tenant's due retries in one pass) and is narrow/read-only.
        `email_next_attempt_at: {"$ne": None, ...}` guards against MongoDB's
        BSON comparison order treating a missing/null value as "less than"
        any date under a bare $lte, which would otherwise also match every
        brand-new, never-yet-attempted Notification."""
        return list(
            self._collection.find(
                {
                    "email_status": "pending",
                    "email_next_attempt_at": {"$ne": None, "$lte": before},
                }
            ).limit(limit)
        )
