from datetime import UTC, datetime
from typing import Any, Literal

from pymongo.database import Database

from procurawise.evaluations.models import MAX_LINKED_VENDORS
from procurawise.shared.tenant_collection import TenantCollection

ReservationOutcome = Literal["reserved", "not_found", "not_draft", "limit_reached"]


class EvaluationRepository:
    def __init__(self, db: Database) -> None:
        self._collection = db["evaluations"]

    def _scoped(self, tenant_id: str) -> TenantCollection:
        return TenantCollection(self._collection, tenant_id)

    def insert(self, tenant_id: str, document: dict[str, Any]) -> None:
        self._scoped(tenant_id).insert_one(document)

    def find_by_id(self, tenant_id: str, evaluation_id: str) -> dict[str, Any] | None:
        return self._scoped(tenant_id).find_one({"_id": evaluation_id})

    def find_many(self, tenant_id: str) -> list[dict[str, Any]]:
        return list(self._scoped(tenant_id).find({}))

    def transition_status(
        self,
        tenant_id: str,
        evaluation_id: str,
        from_status: str,
        to_status: str,
        extra_set: dict[str, Any] | None = None,
    ) -> bool:
        """Atomic, status-conditioned transition - the filter's `status`
        clause is the concurrency guard, no read-check-write race."""
        update = {"status": to_status, "updated_at": datetime.now(UTC)}
        update.update(extra_set or {})
        result = self._scoped(tenant_id).update_one(
            {"_id": evaluation_id, "status": from_status},
            {"$set": update},
        )
        return result.matched_count > 0

    def update_metadata(
        self, tenant_id: str, evaluation_id: str, field_updates: dict[str, Any]
    ) -> bool:
        update = dict(field_updates)
        update["updated_at"] = datetime.now(UTC)
        result = self._scoped(tenant_id).update_one(
            {"_id": evaluation_id, "status": "draft"},
            {"$set": update},
        )
        return result.matched_count > 0

    def add_requirement(
        self, tenant_id: str, evaluation_id: str, requirement_doc: dict[str, Any]
    ) -> bool:
        result = self._scoped(tenant_id).update_one(
            {"_id": evaluation_id, "status": "draft"},
            {"$push": {"requirements": requirement_doc}, "$set": {"updated_at": datetime.now(UTC)}},
        )
        return result.matched_count > 0

    def update_requirement(
        self,
        tenant_id: str,
        evaluation_id: str,
        requirement_id: str,
        field_updates: dict[str, Any],
    ) -> bool:
        positional_set = {f"requirements.$.{key}": value for key, value in field_updates.items()}
        positional_set["requirements.$.updated_at"] = datetime.now(UTC)
        result = self._scoped(tenant_id).update_one(
            {"_id": evaluation_id, "status": "draft", "requirements.id": requirement_id},
            {"$set": positional_set},
        )
        return result.matched_count > 0

    def delete_requirement(self, tenant_id: str, evaluation_id: str, requirement_id: str) -> bool:
        result = self._scoped(tenant_id).update_one(
            {"_id": evaluation_id, "status": "draft"},
            {
                "$pull": {"requirements": {"id": requirement_id}},
                "$set": {"updated_at": datetime.now(UTC)},
            },
        )
        return result.matched_count > 0

    def reserve_vendor_slot(self, tenant_id: str, evaluation_id: str) -> ReservationOutcome:
        """Atomically increments linked_vendor_count only if the evaluation
        is draft and still under the cap - a single-document conditional
        $inc, so two concurrent requests for the 6th/7th slot can never both
        succeed (see plan §12)."""
        result = self._scoped(tenant_id).update_one(
            {
                "_id": evaluation_id,
                "status": "draft",
                "linked_vendor_count": {"$lt": MAX_LINKED_VENDORS},
            },
            {"$inc": {"linked_vendor_count": 1}},
        )
        if result.matched_count > 0:
            return "reserved"

        evaluation = self.find_by_id(tenant_id, evaluation_id)
        if evaluation is None:
            return "not_found"
        if evaluation["status"] != "draft":
            return "not_draft"
        return "limit_reached"

    def release_vendor_slot(self, tenant_id: str, evaluation_id: str) -> None:
        self._scoped(tenant_id).update_one(
            {"_id": evaluation_id},
            {"$inc": {"linked_vendor_count": -1}},
        )
