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

    def find_across_tenants(
        self, *, limit: int, cursor: tuple[datetime, str] | None
    ) -> list[dict[str, Any]]:
        """The `find_across_tenants()` escape hatch ADR 0002/architecture.md
        §5 reserve for `platform_admin` - deliberately bypasses
        TenantCollection, unlike every other method here. Callers (see
        procurawise.admin) must always pair this with a mandatory,
        server-recorded reason and an AuditEvent per tenant touched; nothing
        here enforces that on its own, exactly like MembershipRepository's
        equivalent cross-tenant methods (see identity/repository.py)."""
        filter_: dict[str, Any] = {}
        if cursor is not None:
            cursor_created_at, cursor_id = cursor
            filter_["$or"] = [
                {"created_at": {"$lt": cursor_created_at}},
                {"created_at": cursor_created_at, "_id": {"$lt": cursor_id}},
            ]
        return list(
            self._collection.find(filter_).sort([("created_at", -1), ("_id", -1)]).limit(limit + 1)
        )

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
        self,
        tenant_id: str,
        evaluation_id: str,
        requirement_doc: dict[str, Any],
        extra_set: dict[str, Any] | None = None,
    ) -> bool:
        set_fields = {"updated_at": datetime.now(UTC)}
        set_fields.update(extra_set or {})
        result = self._scoped(tenant_id).update_one(
            {"_id": evaluation_id, "status": "draft"},
            {"$push": {"requirements": requirement_doc}, "$set": set_fields},
        )
        return result.matched_count > 0

    def add_requirements_bulk(
        self,
        tenant_id: str,
        evaluation_id: str,
        requirement_docs: list[dict[str, Any]],
        extra_set: dict[str, Any] | None = None,
    ) -> bool:
        """Fase 11 (knowledge_templates apply): a single atomic $push/$each
        for the whole batch, not N sequential add_requirement calls - avoids
        partial application under a mid-batch failure and avoids N audit
        events for one logical action."""
        set_fields = {"updated_at": datetime.now(UTC)}
        set_fields.update(extra_set or {})
        result = self._scoped(tenant_id).update_one(
            {"_id": evaluation_id, "status": "draft"},
            {"$push": {"requirements": {"$each": requirement_docs}}, "$set": set_fields},
        )
        return result.matched_count > 0

    def update_requirement(
        self,
        tenant_id: str,
        evaluation_id: str,
        requirement_id: str,
        field_updates: dict[str, Any],
        extra_set: dict[str, Any] | None = None,
    ) -> bool:
        positional_set = {f"requirements.$.{key}": value for key, value in field_updates.items()}
        positional_set["requirements.$.updated_at"] = datetime.now(UTC)
        positional_set.update(extra_set or {})
        result = self._scoped(tenant_id).update_one(
            {"_id": evaluation_id, "status": "draft", "requirements.id": requirement_id},
            {"$set": positional_set},
        )
        return result.matched_count > 0

    def delete_requirement(
        self,
        tenant_id: str,
        evaluation_id: str,
        requirement_id: str,
        extra_set: dict[str, Any] | None = None,
    ) -> bool:
        set_fields = {"updated_at": datetime.now(UTC)}
        set_fields.update(extra_set or {})
        result = self._scoped(tenant_id).update_one(
            {"_id": evaluation_id, "status": "draft"},
            {
                "$pull": {"requirements": {"id": requirement_id}},
                "$set": set_fields,
            },
        )
        return result.matched_count > 0

    def reserve_vendor_slot(
        self, tenant_id: str, evaluation_id: str, extra_set: dict[str, Any] | None = None
    ) -> ReservationOutcome:
        """Atomically increments linked_vendor_count only if the evaluation
        is draft and still under the cap - a single-document conditional
        $inc, so two concurrent requests for the 6th/7th slot can never both
        succeed (see plan §12)."""
        update: dict[str, Any] = {"$inc": {"linked_vendor_count": 1}}
        if extra_set:
            update["$set"] = extra_set
        result = self._scoped(tenant_id).update_one(
            {
                "_id": evaluation_id,
                "status": "draft",
                "linked_vendor_count": {"$lt": MAX_LINKED_VENDORS},
            },
            update,
        )
        if result.matched_count > 0:
            return "reserved"

        evaluation = self.find_by_id(tenant_id, evaluation_id)
        if evaluation is None:
            return "not_found"
        if evaluation["status"] != "draft":
            return "not_draft"
        return "limit_reached"

    def release_vendor_slot(
        self, tenant_id: str, evaluation_id: str, extra_set: dict[str, Any] | None = None
    ) -> None:
        update: dict[str, Any] = {"$inc": {"linked_vendor_count": -1}}
        if extra_set:
            update["$set"] = extra_set
        self._scoped(tenant_id).update_one(
            {"_id": evaluation_id},
            update,
        )

    def set_approver(self, tenant_id: str, evaluation_id: str, approver_membership_id: str) -> bool:
        result = self._scoped(tenant_id).update_one(
            {
                "_id": evaluation_id,
                "status": "draft",
                "approval_status": {"$in": ["not_requested", "rejected"]},
            },
            {
                "$set": {
                    "approver_membership_id": approver_membership_id,
                    "updated_at": datetime.now(UTC),
                }
            },
        )
        return result.matched_count > 0

    def backfill_approval_snapshot_id(
        self, tenant_id: str, evaluation_id: str, snapshot_id: str
    ) -> bool:
        """Conditional on approval_snapshot_id being unset (plan §22 step 4)
        - a retry after this already succeeded simply doesn't match, which
        is the expected, harmless outcome, not an error."""
        result = self._scoped(tenant_id).update_one(
            {"_id": evaluation_id, "approval_snapshot_id": None},
            {"$set": {"approval_snapshot_id": snapshot_id, "updated_at": datetime.now(UTC)}},
        )
        return result.matched_count > 0

    def transition_approval_status(
        self,
        tenant_id: str,
        evaluation_id: str,
        from_statuses: tuple[str, ...],
        to_status: str,
        extra_set: dict[str, Any] | None = None,
    ) -> bool:
        """Same atomic-conditional shape as transition_status (Fase 12, plan
        §22/§24), generalized to a $in filter: request_approval is valid
        from two source states (not_requested, rejected)."""
        update = {"approval_status": to_status, "updated_at": datetime.now(UTC)}
        update.update(extra_set or {})
        result = self._scoped(tenant_id).update_one(
            {"_id": evaluation_id, "approval_status": {"$in": list(from_statuses)}},
            {"$set": update},
        )
        return result.matched_count > 0
