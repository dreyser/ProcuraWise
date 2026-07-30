from datetime import UTC, datetime
from typing import Any

from pymongo.database import Database

from procurawise.shared.tenant_collection import TenantCollection


class AssignmentRepository:
    def __init__(self, db: Database) -> None:
        self._collection = db["assignments"]

    def _scoped(self, tenant_id: str) -> TenantCollection:
        return TenantCollection(self._collection, tenant_id)

    def insert(self, tenant_id: str, document: dict[str, Any]) -> None:
        """May raise pymongo.errors.DuplicateKeyError if the same evaluator
        was already assigned to this exact (evaluation, dimension, section)
        concurrently - the service layer translates that into
        DuplicateAssignmentError rather than silently double-inserting."""
        self._scoped(tenant_id).insert_one(document)

    def find_by_id(self, tenant_id: str, assignment_id: str) -> dict[str, Any] | None:
        return self._scoped(tenant_id).find_one({"_id": assignment_id})

    def find_by_natural_key(
        self,
        tenant_id: str,
        evaluation_id: str,
        dimension: str,
        section: str,
        evaluator_membership_id: str,
    ) -> dict[str, Any] | None:
        return self._scoped(tenant_id).find_one(
            {
                "evaluation_id": evaluation_id,
                "dimension": dimension,
                "section": section,
                "evaluator_membership_id": evaluator_membership_id,
            }
        )

    def list_for_evaluation(self, tenant_id: str, evaluation_id: str) -> list[dict[str, Any]]:
        return list(
            self._scoped(tenant_id)
            .find({"evaluation_id": evaluation_id})
            .sort([("dimension", 1), ("section", 1)])
        )

    def list_for_section(
        self, tenant_id: str, evaluation_id: str, dimension: str, section: str
    ) -> list[dict[str, Any]]:
        """Every Assignment recorded for this exact (dimension, section),
        regardless of which evaluator holds it - used by scoring (Fase 9
        Block 3) to decide whether a section is "assigned yet" at all."""
        return list(
            self._scoped(tenant_id).find(
                {"evaluation_id": evaluation_id, "dimension": dimension, "section": section}
            )
        )

    def list_for_evaluator(
        self, tenant_id: str, evaluation_id: str, evaluator_membership_id: str
    ) -> list[dict[str, Any]]:
        return list(
            self._scoped(tenant_id).find(
                {
                    "evaluation_id": evaluation_id,
                    "evaluator_membership_id": evaluator_membership_id,
                }
            )
        )

    def update_status(self, tenant_id: str, assignment_id: str, status: str) -> bool:
        result = self._scoped(tenant_id).update_one(
            {"_id": assignment_id},
            {"$set": {"status": status, "updated_at": datetime.now(UTC)}},
        )
        return result.matched_count > 0

    def delete(self, tenant_id: str, assignment_id: str) -> bool:
        result = self._scoped(tenant_id).delete_one({"_id": assignment_id})
        return result.deleted_count > 0
