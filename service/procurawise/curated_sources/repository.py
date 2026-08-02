from datetime import UTC, datetime
from typing import Any

from pymongo.database import Database


class CuratedSourceRepository:
    """Platform-level content, deliberately NOT wrapped in `TenantCollection`
    (same reasoning as `admin.repository.PlatformAdminAccountRepository`) -
    `CuratedSource` has no `tenant_id` at all; every tenant's
    `CuratedSourceProvider` reads the same rows."""

    def __init__(self, db: Database) -> None:
        self._collection = db["curated_sources"]

    def insert(self, document: dict[str, Any]) -> None:
        self._collection.insert_one(document)

    def find_by_id(self, source_id: str) -> dict[str, Any] | None:
        return self._collection.find_one({"_id": source_id})

    def find_all(self) -> list[dict[str, Any]]:
        return list(self._collection.find({}).sort([("created_at", -1)]))

    def find_active(self) -> list[dict[str, Any]]:
        return list(self._collection.find({"active": True}))

    def update_metadata(self, source_id: str, field_updates: dict[str, Any]) -> bool:
        set_fields = dict(field_updates)
        set_fields["updated_at"] = datetime.now(UTC)
        result = self._collection.update_one({"_id": source_id}, {"$set": set_fields})
        return result.matched_count > 0

    def set_active(self, source_id: str, active: bool) -> bool:
        result = self._collection.update_one(
            {"_id": source_id}, {"$set": {"active": active, "updated_at": datetime.now(UTC)}}
        )
        return result.matched_count > 0
