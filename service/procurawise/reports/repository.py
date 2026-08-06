from typing import Any

from pymongo.database import Database

from procurawise.shared.tenant_collection import TenantCollection


class ReportRepository:
    def __init__(self, db: Database) -> None:
        self._collection = db["reports"]

    def _scoped(self, tenant_id: str) -> TenantCollection:
        return TenantCollection(self._collection, tenant_id)

    def insert(self, tenant_id: str, document: dict[str, Any]) -> None:
        self._scoped(tenant_id).insert_one(document)

    def find_by_id(self, tenant_id: str, report_id: str) -> dict[str, Any] | None:
        return self._scoped(tenant_id).find_one({"_id": report_id})

    def list_for_evaluation(self, tenant_id: str, evaluation_id: str) -> list[dict[str, Any]]:
        return list(
            self._scoped(tenant_id).find({"evaluation_id": evaluation_id}).sort("requested_at", -1)
        )

    def transition_status(
        self,
        tenant_id: str,
        report_id: str,
        from_status: str,
        to_status: str,
        extra_set: dict[str, Any] | None = None,
    ) -> bool:
        """Atomic, status-conditioned transition - same guard pattern as
        AIExecutionRepository.transition_status: the filter's `status` clause
        is the concurrency control, not a read-check-write race."""
        update = dict(extra_set or {})
        update["status"] = to_status
        result = self._scoped(tenant_id).update_one(
            {"_id": report_id, "status": from_status},
            {"$set": update},
        )
        return result.matched_count > 0
