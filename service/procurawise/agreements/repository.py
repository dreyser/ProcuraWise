from typing import Any

from pymongo.database import Database

from procurawise.shared.tenant_collection import TenantCollection


class AgreementRepository:
    """Append-only, like audit.repository.AuditEventRepository: only `insert`
    and read methods exist - never update/delete. A version bump produces a
    new row rather than mutating an old acceptance."""

    def __init__(self, db: Database) -> None:
        self._collection = db["agreements"]

    def _scoped(self, tenant_id: str) -> TenantCollection:
        return TenantCollection(self._collection, tenant_id)

    def insert(self, tenant_id: str, document: dict[str, Any]) -> None:
        self._scoped(tenant_id).insert_one(document)

    def find_latest(
        self, tenant_id: str, user_id: str, agreement_type: str
    ) -> dict[str, Any] | None:
        """Most recent acceptance of `agreement_type` by `user_id`, or None
        if they have never accepted any version of it."""
        cursor = (
            self._scoped(tenant_id)
            .find({"user_id": user_id, "type": agreement_type})
            .sort("accepted_at", -1)
            .limit(1)
        )
        return next(iter(cursor), None)

    def list_for_user(self, tenant_id: str, user_id: str) -> list[dict[str, Any]]:
        return list(self._scoped(tenant_id).find({"user_id": user_id}))
