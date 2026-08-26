from typing import Any

from pymongo.database import Database

from procurawise.shared.tenant_collection import TenantCollection


class CompanyProfileRepository:
    def __init__(self, db: Database) -> None:
        self._collection = db["company_profiles"]

    def _scoped(self, tenant_id: str) -> TenantCollection:
        return TenantCollection(self._collection, tenant_id)

    def insert(self, tenant_id: str, document: dict[str, Any]) -> None:
        self._scoped(tenant_id).insert_one(document)

    def find_by_id(self, tenant_id: str) -> dict[str, Any] | None:
        return self._scoped(tenant_id).find_one({"_id": tenant_id})

    def replace(self, tenant_id: str, document: dict[str, Any]) -> None:
        """`document` has no "$" keys, so TenantCollection.update_one routes
        this to a full-document Collection.replace_one under the hood (see
        its own docstring) - never a $set, so a field dropped from the
        dataclass in a future edit cannot linger as a stale key."""
        self._scoped(tenant_id).update_one({"_id": tenant_id}, document)
