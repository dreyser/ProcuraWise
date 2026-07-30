from typing import Any

from pymongo.database import Database


class PlatformAdminAccountRepository:
    """Deliberately bypasses TenantCollection, like identity.repository's
    UserRepository/TenantRepository - a platform_admin account has no
    tenant_id to scope by at all."""

    def __init__(self, db: Database) -> None:
        self._collection = db["platform_admins"]

    def find_by_id(self, admin_id: str) -> dict[str, Any] | None:
        return self._collection.find_one({"_id": admin_id})

    def find_by_email(self, email: str) -> dict[str, Any] | None:
        return self._collection.find_one({"email": email})

    def insert(self, document: dict[str, Any]) -> None:
        self._collection.insert_one(document)
