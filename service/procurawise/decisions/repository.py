from datetime import UTC, datetime
from typing import Any

from pymongo.database import Database

from procurawise.shared.tenant_collection import TenantCollection

_EDITABLE_STATUSES = ("not_requested", "rejected")


class DecisionRepository:
    def __init__(self, db: Database) -> None:
        self._collection = db["decisions"]

    def _scoped(self, tenant_id: str) -> TenantCollection:
        return TenantCollection(self._collection, tenant_id)

    def insert(self, tenant_id: str, document: dict[str, Any]) -> None:
        self._scoped(tenant_id).insert_one(document)

    def find_by_evaluation_id(self, tenant_id: str, evaluation_id: str) -> dict[str, Any] | None:
        return self._scoped(tenant_id).find_one({"_id": evaluation_id})

    def update_selection(
        self, tenant_id: str, evaluation_id: str, field_updates: dict[str, Any]
    ) -> bool:
        """Only while status is "not_requested"/"rejected" (plan section 12
        state machine) - mirrors evaluations.repository.update_metadata's
        status-conditioned filter as the concurrency guard."""
        update = dict(field_updates)
        update["updated_at"] = datetime.now(UTC)
        result = self._scoped(tenant_id).update_one(
            {"_id": evaluation_id, "status": {"$in": list(_EDITABLE_STATUSES)}},
            {"$set": update},
        )
        return result.matched_count > 0

    def set_approver(self, tenant_id: str, evaluation_id: str, approver_membership_id: str) -> bool:
        result = self._scoped(tenant_id).update_one(
            {"_id": evaluation_id, "status": {"$in": list(_EDITABLE_STATUSES)}},
            {
                "$set": {
                    "approver_membership_id": approver_membership_id,
                    "updated_at": datetime.now(UTC),
                }
            },
        )
        return result.matched_count > 0

    def transition_status(
        self,
        tenant_id: str,
        evaluation_id: str,
        from_statuses: tuple[str, ...],
        to_status: str,
        extra_set: dict[str, Any] | None = None,
    ) -> bool:
        """Atomic, status-conditioned transition - same shape as
        evaluations.repository.transition_approval_status, generalized to a
        DecisionStatus 4-value machine of its own."""
        update = {"status": to_status, "updated_at": datetime.now(UTC)}
        update.update(extra_set or {})
        result = self._scoped(tenant_id).update_one(
            {"_id": evaluation_id, "status": {"$in": list(from_statuses)}},
            {"$set": update},
        )
        return result.matched_count > 0

    def backfill_snapshot_id(self, tenant_id: str, evaluation_id: str, snapshot_id: str) -> bool:
        """Conditional on decision_snapshot_id being unset - a retry after
        this already succeeded simply doesn't match, the expected, harmless
        outcome (same pattern as
        evaluations.repository.backfill_approval_snapshot_id)."""
        result = self._scoped(tenant_id).update_one(
            {"_id": evaluation_id, "decision_snapshot_id": None},
            {"$set": {"decision_snapshot_id": snapshot_id, "updated_at": datetime.now(UTC)}},
        )
        return result.matched_count > 0
