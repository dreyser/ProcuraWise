from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

# Fase 9 (RBAC completo, spec §4): every tenant-scoped buyer/vendor role.
# `platform_admin` is deliberately NOT here - it has no tenant_id claim at all
# (architecture.md §5), so it cannot be a Membership.role; it gets its own
# identity mechanism in the `admin` module instead (see Fase 9 Block 4).
Role = Literal[
    "evaluation_owner",
    "evaluator_functional",
    "evaluator_technical",
    "evaluator_economic",
    "internal_collaborator",
    "approver",
    "tenant_admin",
    "vendor_contact",
]
OidcProviderName = Literal["microsoft", "google"]


def new_id() -> str:
    return uuid4().hex


@dataclass(frozen=True)
class Tenant:
    id: str
    slug: str
    name: str
    created_at: datetime

    @staticmethod
    def create(slug: str, name: str) -> "Tenant":
        return Tenant(id=new_id(), slug=slug, name=name, created_at=datetime.now(UTC))

    def to_document(self) -> dict[str, Any]:
        return {"_id": self.id, "slug": self.slug, "name": self.name, "created_at": self.created_at}

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "Tenant":
        return Tenant(
            id=doc["_id"], slug=doc["slug"], name=doc["name"], created_at=doc["created_at"]
        )


@dataclass(frozen=True)
class OidcIdentity:
    """One linked external identity for a User. Embedded (not a separate
    collection) - always read together with the User, and a person realistically
    links at most one identity per provider (AUTH-PROD, ADR 0003)."""

    provider: OidcProviderName
    subject: str
    linked_at: datetime

    def to_document(self) -> dict[str, Any]:
        return {"provider": self.provider, "subject": self.subject, "linked_at": self.linked_at}

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "OidcIdentity":
        return OidcIdentity(
            provider=doc["provider"], subject=doc["subject"], linked_at=doc["linked_at"]
        )


@dataclass(frozen=True)
class User:
    id: str
    display_name: str
    email: str
    created_at: datetime
    # None means the user only authenticates via a linked OIDC identity below -
    # never has a local password (AUTH-PROD).
    password_hash: str | None = None
    oidc_identities: tuple[OidcIdentity, ...] = ()

    @staticmethod
    def create(display_name: str, email: str, password_hash: str | None = None) -> "User":
        return User(
            id=new_id(),
            display_name=display_name,
            email=email,
            created_at=datetime.now(UTC),
            password_hash=password_hash,
            oidc_identities=(),
        )

    def with_oidc_identity(self, identity: "OidcIdentity") -> "User":
        return replace(self, oidc_identities=(*self.oidc_identities, identity))

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "display_name": self.display_name,
            "email": self.email,
            "created_at": self.created_at,
            "password_hash": self.password_hash,
            "oidc_identities": [identity.to_document() for identity in self.oidc_identities],
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "User":
        return User(
            id=doc["_id"],
            display_name=doc["display_name"],
            email=doc["email"],
            created_at=doc["created_at"],
            password_hash=doc.get("password_hash"),
            oidc_identities=tuple(
                OidcIdentity.from_document(identity) for identity in doc.get("oidc_identities", [])
            ),
        )


@dataclass(frozen=True)
class Membership:
    """A user's binding to one tenant with one role. A single user_id may have
    several Membership rows (different tenants, or different roles within the
    same tenant) - nothing here assumes one tenant per user. In the
    development-identity mechanism, `id` (not `user_id`) is exactly the value
    a client selects via the `X-Dev-Membership-Id` header."""

    id: str
    tenant_id: str
    user_id: str
    role: Role
    vendor_org_id: str | None
    created_at: datetime

    @staticmethod
    def create(
        tenant_id: str, user_id: str, role: Role, vendor_org_id: str | None = None
    ) -> "Membership":
        if role == "vendor_contact" and vendor_org_id is None:
            raise ValueError("vendor_contact membership requires vendor_org_id")
        if role != "vendor_contact" and vendor_org_id is not None:
            raise ValueError("only vendor_contact memberships may set vendor_org_id")
        return Membership(
            id=new_id(),
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            vendor_org_id=vendor_org_id,
            created_at=datetime.now(UTC),
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "role": self.role,
            "vendor_org_id": self.vendor_org_id,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "Membership":
        return Membership(
            id=doc["_id"],
            tenant_id=doc["tenant_id"],
            user_id=doc["user_id"],
            role=doc["role"],
            vendor_org_id=doc.get("vendor_org_id"),
            created_at=doc["created_at"],
        )


@dataclass(frozen=True)
class VendorOrganization:
    """Tenant-scoped by design: each buyer tenant maintains its own vendor
    records rather than sharing a cross-tenant vendor directory, so "a vendor
    cannot enumerate other vendors" holds trivially - there is no query shape
    that could ever cross a tenant boundary to find one."""

    id: str
    tenant_id: str
    name: str
    created_at: datetime

    @staticmethod
    def create(tenant_id: str, name: str) -> "VendorOrganization":
        return VendorOrganization(
            id=new_id(), tenant_id=tenant_id, name=name, created_at=datetime.now(UTC)
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "VendorOrganization":
        return VendorOrganization(
            id=doc["_id"],
            tenant_id=doc["tenant_id"],
            name=doc["name"],
            created_at=doc["created_at"],
        )


VendorInvitationStatus = Literal["pending", "accepted", "revoked"]


@dataclass(frozen=True)
class VendorInvitation:
    """A single-use invitation binding one email address to one pre-created
    `vendor_contact` Membership (Fase 15). `token_hash` is a deterministic
    SHA-256 digest, not a slow password hash - the raw token itself already
    carries enough entropy (secrets.token_urlsafe(32)), and a deterministic
    digest is what allows the redemption lookup to be a single indexed exact
    match instead of iterating every pending invitation. The raw token is
    never persisted, logged in audit metadata, or returned again after
    issuance."""

    id: str
    tenant_id: str
    vendor_org_id: str
    membership_id: str
    email: str
    token_hash: str
    status: VendorInvitationStatus
    invited_by_membership_id: str
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None

    @staticmethod
    def create(
        *,
        tenant_id: str,
        vendor_org_id: str,
        membership_id: str,
        email: str,
        token_hash: str,
        invited_by_membership_id: str,
        ttl_days: int,
    ) -> "VendorInvitation":
        now = datetime.now(UTC)
        return VendorInvitation(
            id=new_id(),
            tenant_id=tenant_id,
            vendor_org_id=vendor_org_id,
            membership_id=membership_id,
            email=email,
            token_hash=token_hash,
            status="pending",
            invited_by_membership_id=invited_by_membership_id,
            created_at=now,
            expires_at=now + timedelta(days=ttl_days),
            accepted_at=None,
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "tenant_id": self.tenant_id,
            "vendor_org_id": self.vendor_org_id,
            "membership_id": self.membership_id,
            "email": self.email,
            "token_hash": self.token_hash,
            "status": self.status,
            "invited_by_membership_id": self.invited_by_membership_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "accepted_at": self.accepted_at,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "VendorInvitation":
        return VendorInvitation(
            id=doc["_id"],
            tenant_id=doc["tenant_id"],
            vendor_org_id=doc["vendor_org_id"],
            membership_id=doc["membership_id"],
            email=doc["email"],
            token_hash=doc["token_hash"],
            status=doc["status"],
            invited_by_membership_id=doc["invited_by_membership_id"],
            created_at=doc["created_at"],
            expires_at=doc["expires_at"],
            accepted_at=doc.get("accepted_at"),
        )
