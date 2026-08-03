from typing import Any

from pymongo.database import Database

from procurawise.shared.tenant_collection import TenantCollection


class DocumentRepository:
    def __init__(self, db: Database) -> None:
        self._collection = db["documents"]

    def _scoped(self, tenant_id: str) -> TenantCollection:
        return TenantCollection(self._collection, tenant_id)

    def insert(self, tenant_id: str, document: dict[str, Any]) -> None:
        self._scoped(tenant_id).insert_one(document)

    def find_by_id(self, tenant_id: str, document_id: str) -> dict[str, Any] | None:
        return self._scoped(tenant_id).find_one({"_id": document_id})

    def find_current_for_slot(
        self, tenant_id: str, proposal_id: str, requirement_id: str | None
    ) -> dict[str, Any] | None:
        """The one `current` row for a given (proposal_id, requirement_id)
        evidence slot - only meaningful when requirement_id is not None
        (general, requirement_id=None attachments have no single-slot
        semantics, see documents.models.Document docstring)."""
        return self._scoped(tenant_id).find_one(
            {"proposal_id": proposal_id, "requirement_id": requirement_id, "status": "current"}
        )

    def list_for_proposal(self, tenant_id: str, proposal_id: str) -> list[dict[str, Any]]:
        """Every non-deleted row (current and superseded) - callers that only
        want the active set filter status=="current" themselves; keeping
        superseded rows in this list lets the UI show version history."""
        return list(
            self._scoped(tenant_id)
            .find({"proposal_id": proposal_id})
            .sort([("requirement_id", 1), ("version", 1)])
        )

    def list_current_for_proposal(self, tenant_id: str, proposal_id: str) -> list[dict[str, Any]]:
        return list(self._scoped(tenant_id).find({"proposal_id": proposal_id, "status": "current"}))

    def mark_superseded(self, tenant_id: str, document_id: str) -> None:
        self._scoped(tenant_id).update_one({"_id": document_id}, {"$set": {"status": "superseded"}})

    def delete(self, tenant_id: str, document_id: str) -> bool:
        result = self._scoped(tenant_id).delete_one({"_id": document_id, "status": "current"})
        return result.deleted_count > 0
