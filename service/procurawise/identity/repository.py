from typing import Any

from pymongo.database import Database

from procurawise.shared.tenant_collection import TenantCollection


class TenantRepository:
    """Tenants are not tenant-owned data (there is no tenant_id to scope by),
    so this talks to the plain collection directly rather than through
    TenantCollection."""

    def __init__(self, db: Database) -> None:
        self._collection = db["tenants"]

    def find_by_id(self, tenant_id: str) -> dict[str, Any] | None:
        return self._collection.find_one({"_id": tenant_id})

    def find_by_slug(self, slug: str) -> dict[str, Any] | None:
        return self._collection.find_one({"slug": slug})

    def insert(self, document: dict[str, Any]) -> None:
        self._collection.insert_one(document)


class UserRepository:
    """Users are not tenant-owned (a user may hold Membership rows in several
    tenants), so this also bypasses TenantCollection."""

    def __init__(self, db: Database) -> None:
        self._collection = db["users"]

    def find_by_id(self, user_id: str) -> dict[str, Any] | None:
        return self._collection.find_one({"_id": user_id})

    def find_by_email(self, email: str) -> dict[str, Any] | None:
        return self._collection.find_one({"email": email})

    def insert(self, document: dict[str, Any]) -> None:
        self._collection.insert_one(document)


class MembershipRepository:
    """`find_by_id` and `list_all_for_dev` deliberately read outside any
    single tenant's scope: resolving a development actor from a bare
    membership_id (or listing every seeded actor for the dev picker) has no
    tenant to scope by yet - that tenant is exactly what's being resolved.
    This mirrors the `find_across_tenants()` escape hatch ADR 0002 reserves
    for platform_admin. Both must only ever be reachable from code already
    gated to development/test (see identity.dev_provider)."""

    def __init__(self, db: Database) -> None:
        self._collection = db["memberships"]

    def find_by_id(self, membership_id: str) -> dict[str, Any] | None:
        return self._collection.find_one({"_id": membership_id})

    def find_one_for(
        self, tenant_id: str, user_id: str, role: str, vendor_org_id: str | None
    ) -> dict[str, Any] | None:
        return self._collection.find_one(
            {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "role": role,
                "vendor_org_id": vendor_org_id,
            }
        )

    def list_all_for_dev(self) -> list[dict[str, Any]]:
        return list(self._collection.find({}))

    def insert(self, document: dict[str, Any]) -> None:
        self._collection.insert_one(document)


class VendorOrganizationRepository:
    """Vendor organizations are tenant-owned business data, so every access
    goes through TenantCollection, scoped per-call to the caller's tenant."""

    def __init__(self, db: Database) -> None:
        self._collection = db["vendor_organizations"]

    def find_by_name(self, tenant_id: str, name: str) -> dict[str, Any] | None:
        return TenantCollection(self._collection, tenant_id).find_one({"name": name})

    def insert(self, tenant_id: str, document: dict[str, Any]) -> None:
        TenantCollection(self._collection, tenant_id).insert_one(document)
