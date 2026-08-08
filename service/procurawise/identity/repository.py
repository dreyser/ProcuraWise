import re
from datetime import datetime
from typing import Any

from pymongo.database import Database

from procurawise.shared.tenant_collection import TenantCollection

VendorOrganizationCursor = tuple[str, str]


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

    def update_oidc_identities(self, user_id: str, oidc_identities: list[dict[str, Any]]) -> None:
        """Just-in-time-link step of the OIDC callback (AUTH-PROD): replaces
        the whole embedded list, never appended to piecemeal by an operator
        other than the identity module itself."""
        self._collection.update_one(
            {"_id": user_id}, {"$set": {"oidc_identities": oidc_identities}}
        )

    def update_password(self, user_id: str, password_hash: str) -> None:
        """Fase 15: sets/replaces the password a vendor_contact chooses while
        redeeming their invitation - same shape as the OIDC linking above,
        a single authoritative field, never appended to piecemeal."""
        self._collection.update_one({"_id": user_id}, {"$set": {"password_hash": password_hash}})


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

    def find_by_id_and_tenant(self, membership_id: str, tenant_id: str) -> dict[str, Any] | None:
        """Tenant-scoped membership lookup for callers (e.g. `assignments`)
        that must verify a target membership_id both exists and belongs to
        the caller's own tenant, without `find_by_id`'s cross-tenant reach."""
        return self._collection.find_one({"_id": membership_id, "tenant_id": tenant_id})

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

    def find_vendor_contacts_for_org(
        self, tenant_id: str, vendor_org_id: str
    ) -> list[dict[str, Any]]:
        """Every vendor_contact Membership under one VendorOrganization -
        Fase 24 (notifications): backs fan-out for events where a whole
        vendor org's collaborators are the "affected" party (qna_answer_
        published when published_anonymized, proposal_submitted/reopened),
        not just the single contact who happened to trigger the action."""
        return list(
            self._collection.find(
                {"tenant_id": tenant_id, "vendor_org_id": vendor_org_id, "role": "vendor_contact"}
            )
        )

    def find_all_for_tenant(self, tenant_id: str) -> list[dict[str, Any]]:
        """Every Membership row within a single tenant - unlike
        `find_all_for_user`/`list_all_for_dev`, this one *is* naturally
        tenant-scoped (a real, hard-coded `tenant_id` match, not a
        client-controlled filter), backing `tenant_admin`'s "Usuarios, roles"
        capability (spec §4). Still bypasses TenantCollection directly
        rather than its wrapper, consistent with the rest of this
        repository."""
        return list(self._collection.find({"tenant_id": tenant_id}))

    def find_all_for_user(self, user_id: str) -> list[dict[str, Any]]:
        """Every Membership row for a user across all tenants/roles - reads
        outside any single tenant's scope for the same reason
        `list_all_for_dev`/`find_by_id` do (see class docstring): resolving
        "which tenants can this authenticated user act in" has no tenant to
        scope by yet. Used by AUTH-PROD's GET /auth/memberships, gated to the
        caller's own user_id (proven by their pre-session/access token), never
        client-supplied."""
        return list(self._collection.find({"user_id": user_id}))

    def insert(self, document: dict[str, Any]) -> None:
        self._collection.insert_one(document)


class VendorOrganizationRepository:
    """Vendor organizations are tenant-owned business data, so every access
    goes through TenantCollection, scoped per-call to the caller's tenant."""

    def __init__(self, db: Database) -> None:
        self._collection = db["vendor_organizations"]

    def find_by_name(self, tenant_id: str, name: str) -> dict[str, Any] | None:
        return TenantCollection(self._collection, tenant_id).find_one({"name": name})

    def find_by_id(self, tenant_id: str, vendor_org_id: str) -> dict[str, Any] | None:
        return TenantCollection(self._collection, tenant_id).find_one({"_id": vendor_org_id})

    def insert(self, tenant_id: str, document: dict[str, Any]) -> None:
        TenantCollection(self._collection, tenant_id).insert_one(document)

    def find_many(
        self,
        tenant_id: str,
        *,
        search: str | None,
        limit: int,
        cursor: VendorOrganizationCursor | None,
    ) -> list[dict[str, Any]]:
        """Stable-order (name, id) catalog page. Fetches `limit + 1` so the
        caller can tell whether a next page exists without a second query."""
        filter_: dict[str, Any] = {}
        if search:
            filter_["name"] = {"$regex": re.escape(search), "$options": "i"}
        if cursor is not None:
            cursor_name, cursor_id = cursor
            filter_["$or"] = [
                {"name": {"$gt": cursor_name}},
                {"name": cursor_name, "_id": {"$gt": cursor_id}},
            ]
        scoped = TenantCollection(self._collection, tenant_id)
        results = scoped.find(filter_).sort([("name", 1), ("_id", 1)]).limit(limit + 1)
        return list(results)


class VendorInvitationRepository:
    """`find_by_token_hash_unscoped` is a deliberate, documented bypass of
    TenantCollection - redeeming an invitation link is exactly the moment
    the caller does not yet know which tenant it belongs to (there is no
    membership/JWT to derive it from yet). This mirrors the same rationale
    MembershipRepository.find_by_id/list_all_for_dev and
    admin.find_across_tenants() already document: the escape hatch is
    reachable only from code that has no tenant to scope by yet, never from
    an authenticated buyer/vendor request. Every other method here is
    tenant-scoped once tenant_id is already known (from the found
    invitation's own document, or from an authenticated buyer's context)."""

    def __init__(self, db: Database) -> None:
        self._collection = db["vendor_invitations"]

    def _scoped(self, tenant_id: str) -> TenantCollection:
        return TenantCollection(self._collection, tenant_id)

    def insert(self, tenant_id: str, document: dict[str, Any]) -> None:
        self._scoped(tenant_id).insert_one(document)

    def find_by_token_hash_unscoped(self, token_hash: str) -> dict[str, Any] | None:
        return self._collection.find_one({"token_hash": token_hash})

    def find_by_id(self, tenant_id: str, invitation_id: str) -> dict[str, Any] | None:
        return self._scoped(tenant_id).find_one({"_id": invitation_id})

    def find_by_vendor_org(self, tenant_id: str, vendor_org_id: str) -> list[dict[str, Any]]:
        return list(self._scoped(tenant_id).find({"vendor_org_id": vendor_org_id}))

    def try_accept(self, tenant_id: str, invitation_id: str, now: datetime) -> bool:
        """Atomic conditional transition: pending -> accepted, only if not
        already expired. Returns whether *this* call won the transition -
        the caller must treat False (already accepted/revoked/expired, or
        raced by a concurrent redemption of the same token) identically to
        "token not found", never distinguishing the reason to the client."""
        result = self._scoped(tenant_id).update_one(
            {"_id": invitation_id, "status": "pending", "expires_at": {"$gt": now}},
            {"$set": {"status": "accepted", "accepted_at": now}},
        )
        return result.modified_count == 1

    def try_revoke(self, tenant_id: str, invitation_id: str) -> bool:
        result = self._scoped(tenant_id).update_one(
            {"_id": invitation_id, "status": "pending"},
            {"$set": {"status": "revoked"}},
        )
        return result.modified_count == 1
