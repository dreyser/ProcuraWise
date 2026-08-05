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

    def replace_cost_items(
        self,
        tenant_id: str,
        proposal_id: str,
        expected_version: int,
        cost_items: list[dict[str, Any]],
    ) -> bool:
        """Fase 19 - same whole-array-replace + version-conditioned pattern
        as replace_answers above."""
        result = self._scoped(tenant_id).update_one(
            {"_id": proposal_id, "status": "draft", "version": expected_version},
            {
                "$set": {"cost_items": cost_items, "updated_at": datetime.now(UTC)},
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
        """Fase 21 (ADR 0013): appends to `snapshots` (`$push`) rather than
        overwriting a single slot (`$set`) - this is what makes a second
        round's submit() preserve Ronda 0's snapshot instead of clobbering
        it. Still conditioned on `status="draft"` + `version=expected_version`,
        same optimistic-concurrency guard as every other write here - true
        both for the very first submit (Ronda 0) and for a resubmit after
        `reopen()` (Ronda 1)."""
        result = self._scoped(tenant_id).update_one(
            {"_id": proposal_id, "status": "draft", "version": expected_version},
            {
                "$set": {
                    "status": "submitted",
                    "submitted_at": submitted_at,
                    "updated_at": submitted_at,
                },
                "$push": {"snapshots": snapshot},
                "$inc": {"version": 1},
            },
        )
        return result.matched_count > 0

    def reopen(
        self,
        tenant_id: str,
        proposal_id: str,
        *,
        new_round: int,
        answers: list[dict[str, Any]],
        cost_items: list[dict[str, Any]],
        reason: str,
        reopened_at: datetime,
        reopened_by_membership_id: str,
    ) -> bool:
        """Fase 21 (ADR 0013/FR-047) - `submitted -> draft` for a single
        proposal, carrying forward its last snapshot's answers/cost_items
        (already marked `status="inherited"` by the caller) as the new
        editable draft. Conditioned on `status="submitted"` - the same
        precondition ProposalService.reopen() already checked, re-asserted
        here atomically so a concurrent reopen (or a submit racing a reopen)
        can never both succeed."""
        result = self._scoped(tenant_id).update_one(
            {"_id": proposal_id, "status": "submitted"},
            {
                "$set": {
                    "status": "draft",
                    "round": new_round,
                    "answers": answers,
                    "cost_items": cost_items,
                    "reopened_reason": reason,
                    "reopened_at": reopened_at,
                    "reopened_by_membership_id": reopened_by_membership_id,
                    "updated_at": reopened_at,
                },
                "$inc": {"version": 1},
            },
        )
        return result.matched_count > 0
