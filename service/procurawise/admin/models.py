from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def new_id() -> str:
    return uuid4().hex


@dataclass(frozen=True)
class PlatformAdminAccount:
    """`platform_admin` (spec §4: "Administrador de plataforma") is
    deliberately NOT a `Membership` - it has no `tenant_id` claim at all
    (architecture.md §5), so it cannot reuse `identity.models.Membership`,
    which requires one. This is its own minimal, tenant-less account,
    provisioned the same way buyer accounts are (procurawise.provisioning_cli
    pattern: no self-signup, no HTTP registration endpoint - see Fase 9 Block
    4 scope note in session-handoff.md)."""

    id: str
    email: str
    display_name: str
    password_hash: str
    created_at: datetime

    @staticmethod
    def create(email: str, display_name: str, password_hash: str) -> "PlatformAdminAccount":
        return PlatformAdminAccount(
            id=new_id(),
            email=email,
            display_name=display_name,
            password_hash=password_hash,
            created_at=datetime.now(UTC),
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "email": self.email,
            "display_name": self.display_name,
            "password_hash": self.password_hash,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "PlatformAdminAccount":
        return PlatformAdminAccount(
            id=doc["_id"],
            email=doc["email"],
            display_name=doc["display_name"],
            password_hash=doc["password_hash"],
            created_at=doc["created_at"],
        )
