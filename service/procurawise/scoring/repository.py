from datetime import UTC, datetime
from typing import Any

from pymongo.database import Database

from procurawise.shared.tenant_collection import TenantCollection


class ScoreRepository:
    def __init__(self, db: Database) -> None:
        self._collection = db["scores"]

    def _scoped(self, tenant_id: str) -> TenantCollection:
        return TenantCollection(self._collection, tenant_id)

    def insert(self, tenant_id: str, document: dict[str, Any]) -> None:
        """May raise pymongo.errors.DuplicateKeyError if a score for this
        natural key was created concurrently - the caller (service layer)
        translates that into a conflict rather than silently overwriting."""
        self._scoped(tenant_id).insert_one(document)

    def find_one_by_natural_key(
        self,
        tenant_id: str,
        evaluation_id: str,
        proposal_id: str,
        snapshot_id: str,
        requirement_id: str,
    ) -> dict[str, Any] | None:
        return self._scoped(tenant_id).find_one(
            {
                "evaluation_id": evaluation_id,
                "proposal_id": proposal_id,
                "snapshot_id": snapshot_id,
                "requirement_id": requirement_id,
            }
        )

    def find_by_proposal(self, tenant_id: str, proposal_id: str) -> list[dict[str, Any]]:
        return list(self._scoped(tenant_id).find({"proposal_id": proposal_id}))

    def update(
        self,
        tenant_id: str,
        score_id: str,
        expected_version: int,
        score: int,
        comment: str | None,
        membership_id: str,
        source_ai_execution_id: str | None = None,
    ) -> bool:
        result = self._scoped(tenant_id).update_one(
            {"_id": score_id, "version": expected_version},
            {
                "$set": {
                    "score": score,
                    "comment": comment,
                    "updated_by_membership_id": membership_id,
                    "updated_at": datetime.now(UTC),
                    "source_ai_execution_id": source_ai_execution_id,
                },
                "$inc": {"version": 1},
            },
        )
        return result.matched_count > 0
