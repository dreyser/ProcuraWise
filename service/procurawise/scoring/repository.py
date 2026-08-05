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


class EconomicAssessmentRepository:
    """Fase 20 (ADR 0009) - one document per (tenant_id, evaluation_id,
    proposal_id), same TenantCollection/optimistic-concurrency pattern as
    ScoreRepository above, but a single upsert-able document instead of one
    row per criterion (the 10-criterion set is fixed and always edited as a
    whole, see scoring.models.EconomicAssessment)."""

    def __init__(self, db: Database) -> None:
        self._collection = db["economic_assessments"]

    def _scoped(self, tenant_id: str) -> TenantCollection:
        return TenantCollection(self._collection, tenant_id)

    def insert(self, tenant_id: str, document: dict[str, Any]) -> None:
        """May raise pymongo.errors.DuplicateKeyError on a concurrent first
        write for the same proposal - the caller translates that into a
        conflict, same as ScoreRepository.insert."""
        self._scoped(tenant_id).insert_one(document)

    def find_by_evaluation_and_proposal(
        self, tenant_id: str, evaluation_id: str, proposal_id: str
    ) -> dict[str, Any] | None:
        return self._scoped(tenant_id).find_one(
            {"evaluation_id": evaluation_id, "proposal_id": proposal_id}
        )

    def find_by_evaluation(self, tenant_id: str, evaluation_id: str) -> list[dict[str, Any]]:
        return list(self._scoped(tenant_id).find({"evaluation_id": evaluation_id}))

    def update(
        self,
        tenant_id: str,
        assessment_id: str,
        expected_version: int,
        commercial_scores: list[dict[str, Any]],
        risk_scores: list[dict[str, Any]],
        membership_id: str,
    ) -> bool:
        result = self._scoped(tenant_id).update_one(
            {"_id": assessment_id, "version": expected_version},
            {
                "$set": {
                    "commercial_scores": commercial_scores,
                    "risk_scores": risk_scores,
                    "updated_by_membership_id": membership_id,
                    "updated_at": datetime.now(UTC),
                },
                "$inc": {"version": 1},
            },
        )
        return result.matched_count > 0
