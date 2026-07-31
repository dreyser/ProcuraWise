from typing import Any

from pymongo.database import Database

from procurawise.shared.tenant_collection import TenantCollection


class EvaluationSnapshotRepository:
    """Deliberately exposes only `insert` (insert) and `find_by_evaluation_id`
    (read) - never `update`/`delete`/`replace` - mirroring
    audit.repository.AuditEventRepository's immutability-by-API-surface
    pattern (plan §21). No code path in this class can mutate or remove a
    persisted EvaluationSnapshot."""

    def __init__(self, db: Database) -> None:
        self._collection = db["evaluation_snapshots"]

    def _scoped(self, tenant_id: str) -> TenantCollection:
        return TenantCollection(self._collection, tenant_id)

    def insert(self, tenant_id: str, document: dict[str, Any]) -> None:
        self._scoped(tenant_id).insert_one(document)

    def find_by_evaluation_id(self, tenant_id: str, evaluation_id: str) -> dict[str, Any] | None:
        return self._scoped(tenant_id).find_one({"evaluation_id": evaluation_id})
