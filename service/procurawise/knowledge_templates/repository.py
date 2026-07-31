from datetime import UTC, datetime
from typing import Any

from pymongo.database import Database

from procurawise.shared.tenant_collection import TenantCollection


class KnowledgeTemplateRepository:
    def __init__(self, db: Database) -> None:
        self._collection = db["knowledge_templates"]

    def _scoped(self, tenant_id: str) -> TenantCollection:
        return TenantCollection(self._collection, tenant_id)

    def insert(self, tenant_id: str, document: dict[str, Any]) -> None:
        self._scoped(tenant_id).insert_one(document)

    def find_by_id(self, tenant_id: str, template_id: str) -> dict[str, Any] | None:
        return self._scoped(tenant_id).find_one({"_id": template_id})

    def find_many(self, tenant_id: str) -> list[dict[str, Any]]:
        return list(self._scoped(tenant_id).find({}).sort([("created_at", -1)]))

    def update_metadata(
        self, tenant_id: str, template_id: str, field_updates: dict[str, Any]
    ) -> bool:
        set_fields = dict(field_updates)
        set_fields["updated_at"] = datetime.now(UTC)
        result = self._scoped(tenant_id).update_one({"_id": template_id}, {"$set": set_fields})
        return result.matched_count > 0

    def push_item(self, tenant_id: str, template_id: str, item_doc: dict[str, Any]) -> bool:
        result = self._scoped(tenant_id).update_one(
            {"_id": template_id},
            {
                "$push": {"items": item_doc},
                "$set": {"updated_at": datetime.now(UTC)},
            },
        )
        return result.matched_count > 0

    def update_item(
        self,
        tenant_id: str,
        template_id: str,
        item_id: str,
        field_updates: dict[str, Any],
    ) -> bool:
        positional_set = {f"items.$.{key}": value for key, value in field_updates.items()}
        positional_set["items.$.updated_at"] = datetime.now(UTC)
        positional_set["updated_at"] = datetime.now(UTC)
        result = self._scoped(tenant_id).update_one(
            {"_id": template_id, "items.id": item_id},
            {"$set": positional_set},
        )
        return result.matched_count > 0

    def delete_item(self, tenant_id: str, template_id: str, item_id: str) -> bool:
        result = self._scoped(tenant_id).update_one(
            {"_id": template_id},
            {
                "$pull": {"items": {"id": item_id}},
                "$set": {"updated_at": datetime.now(UTC)},
            },
        )
        return result.matched_count > 0

    def delete(self, tenant_id: str, template_id: str) -> bool:
        result = self._scoped(tenant_id).delete_one({"_id": template_id})
        return result.deleted_count > 0
