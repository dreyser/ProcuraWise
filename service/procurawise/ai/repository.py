from typing import Any

from pymongo.database import Database

from procurawise.shared.tenant_collection import TenantCollection


class AIExecutionRepository:
    def __init__(self, db: Database) -> None:
        self._collection = db["ai_executions"]

    def _scoped(self, tenant_id: str) -> TenantCollection:
        return TenantCollection(self._collection, tenant_id)

    def insert(self, tenant_id: str, document: dict[str, Any]) -> None:
        self._scoped(tenant_id).insert_one(document)

    def find_by_id(self, tenant_id: str, execution_id: str) -> dict[str, Any] | None:
        return self._scoped(tenant_id).find_one({"_id": execution_id})

    def transition_status(
        self,
        tenant_id: str,
        execution_id: str,
        from_status: str,
        to_status: str,
        extra_set: dict[str, Any] | None = None,
    ) -> bool:
        """Atomic, status-conditioned transition - same guard pattern as
        `EvaluationRepository.transition_status`: the filter's `status`
        clause is the concurrency control, not a read-check-write race. Used
        by the worker to move queued->running->succeeded/failed."""
        update = dict(extra_set or {})
        update["status"] = to_status
        result = self._scoped(tenant_id).update_one(
            {"_id": execution_id, "status": from_status},
            {"$set": update},
        )
        return result.matched_count > 0

    def record_acceptance(
        self, tenant_id: str, execution_id: str, accepted_requirement_ids: list[str]
    ) -> bool:
        result = self._scoped(tenant_id).update_one(
            {"_id": execution_id},
            {"$set": {"accepted_requirement_ids": accepted_requirement_ids}},
        )
        return result.matched_count > 0
