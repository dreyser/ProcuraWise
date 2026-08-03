from typing import Any

from pymongo.database import Database

from procurawise.shared.tenant_collection import TenantCollection


class QuestionRepository:
    def __init__(self, db: Database) -> None:
        self._collection = db["qna_questions"]

    def _scoped(self, tenant_id: str) -> TenantCollection:
        return TenantCollection(self._collection, tenant_id)

    def insert(self, tenant_id: str, document: dict[str, Any]) -> None:
        self._scoped(tenant_id).insert_one(document)

    def find_by_id(self, tenant_id: str, question_id: str) -> dict[str, Any] | None:
        return self._scoped(tenant_id).find_one({"_id": question_id})

    def list_for_proposal(self, tenant_id: str, proposal_id: str) -> list[dict[str, Any]]:
        """Vendor's own view of its Proposal's Q&A - every status, own
        questions only (already proposal-scoped, so already vendor_org_id-
        scoped transitively, same authorization anchor as documents)."""
        return list(
            self._scoped(tenant_id).find({"proposal_id": proposal_id}).sort("created_at", 1)
        )

    def list_for_evaluation_as_buyer(
        self, tenant_id: str, evaluation_id: str
    ) -> list[dict[str, Any]]:
        """Buyer's view - every question across every vendor in the
        evaluation, every status, real identity untouched (no visibility
        filter - that projection only applies to the cross-vendor read)."""
        return list(
            self._scoped(tenant_id).find({"evaluation_id": evaluation_id}).sort("created_at", 1)
        )

    def list_published_for_evaluation(
        self, tenant_id: str, evaluation_id: str, exclude_vendor_org_id: str
    ) -> list[dict[str, Any]]:
        """What a vendor sees of its peers - only questions with a current
        answer visibility of "published_anonymized", never its own
        (excluded here since the vendor already gets its own via
        list_for_proposal, regardless of visibility)."""
        return list(
            self._scoped(tenant_id)
            .find(
                {
                    "evaluation_id": evaluation_id,
                    "vendor_org_id": {"$ne": exclude_vendor_org_id},
                    "current_answer.visibility": "published_anonymized",
                }
            )
            .sort("created_at", 1)
        )

    def withdraw(self, tenant_id: str, question_id: str) -> bool:
        """Physical delete, conditioned on status=="open" - nothing
        references a never-answered question yet (same reasoning as
        Document pre-submit delete, Fase 16 R9)."""
        result = self._scoped(tenant_id).delete_one({"_id": question_id, "status": "open"})
        return result.deleted_count > 0

    def publish_answer(
        self,
        tenant_id: str,
        question_id: str,
        expected_version: int,
        *,
        current_answer: dict[str, Any],
        answer_history: list[dict[str, Any]],
    ) -> bool:
        """Single conditioned update - the caller (QuestionService) has
        already computed the new current_answer and the history with the
        prior current_answer appended (if any); this only applies it
        atomically, conditioned on the document's own optimistic-
        concurrency version (same pattern as ProposalRepository.submit)."""
        result = self._scoped(tenant_id).update_one(
            {"_id": question_id, "version": expected_version},
            {
                "$set": {
                    "current_answer": current_answer,
                    "answer_history": answer_history,
                    "status": "answered",
                },
                "$inc": {"version": 1},
            },
        )
        return result.matched_count > 0
