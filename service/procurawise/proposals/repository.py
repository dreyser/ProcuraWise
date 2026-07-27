from datetime import UTC, datetime
from typing import Any

from pymongo.database import Database

from procurawise.shared.tenant_collection import TenantCollection


class ProposalRepository:
    def __init__(self, db: Database) -> None:
        self._collection = db["proposals"]

    def _scoped(self, tenant_id: str) -> TenantCollection:
        return TenantCollection(self._collection, tenant_id)

    def insert(self, tenant_id: str, document: dict[str, Any]) -> None:
        self._scoped(tenant_id).insert_one(document)

    def find_by_id(self, tenant_id: str, proposal_id: str) -> dict[str, Any] | None:
        return self._scoped(tenant_id).find_one({"_id": proposal_id})

    def find_by_evaluation(self, tenant_id: str, evaluation_id: str) -> list[dict[str, Any]]:
        return list(self._scoped(tenant_id).find({"evaluation_id": evaluation_id}))

    def find_one_by_evaluation_and_vendor(
        self, tenant_id: str, evaluation_id: str, vendor_org_id: str
    ) -> dict[str, Any] | None:
        return self._scoped(tenant_id).find_one(
            {"evaluation_id": evaluation_id, "vendor_org_id": vendor_org_id}
        )

    def find_by_vendor_org(self, tenant_id: str, vendor_org_id: str) -> list[dict[str, Any]]:
        return list(self._scoped(tenant_id).find({"vendor_org_id": vendor_org_id}))

    def delete(self, tenant_id: str, proposal_id: str) -> bool:
        result = self._scoped(tenant_id).delete_one({"_id": proposal_id, "status": "draft"})
        return result.deleted_count > 0

    def replace_answers(
        self,
        tenant_id: str,
        proposal_id: str,
        expected_version: int,
        answers: list[dict[str, Any]],
    ) -> bool:
        """Conditioned on status=draft AND version=expected_version - the
        version match is the concurrency guard (see plan §12); the whole
        `answers` array is replaced rather than patched in place because
        Mongo has no clean atomic "upsert-or-update array element by key"
        primitive without arrayFilters edge cases, and the array is small
        (bounded by requirement count)."""
        result = self._scoped(tenant_id).update_one(
            {"_id": proposal_id, "status": "draft", "version": expected_version},
            {
                "$set": {"answers": answers, "updated_at": datetime.now(UTC)},
                "$inc": {"version": 1},
            },
        )
        return result.matched_count > 0

    def submit(
        self,
        tenant_id: str,
        proposal_id: str,
        expected_version: int,
        snapshot: dict[str, Any],
        submitted_at: datetime,
    ) -> bool:
        result = self._scoped(tenant_id).update_one(
            {"_id": proposal_id, "status": "draft", "version": expected_version},
            {
                "$set": {
                    "status": "submitted",
                    "snapshot": snapshot,
                    "submitted_at": submitted_at,
                    "updated_at": submitted_at,
                },
                "$inc": {"version": 1},
            },
        )
        return result.matched_count > 0
