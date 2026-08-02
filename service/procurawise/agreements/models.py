from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

AgreementType = Literal["nda", "conflict_of_interest"]


def new_id() -> str:
    return uuid4().hex


@dataclass(frozen=True)
class Agreement:
    """Append-only acceptance record (Fase 15, ADR 0014): one vendor_contact's
    proof of acceptance of one version of a legal document. Never
    updated/deleted - a version bump produces a *new* Agreement row rather
    than mutating an old one, so full acceptance history is always kept
    (same discipline as audit.models.AuditEvent). Grain is `user_id`, not
    `vendor_org_id` (ADR 0014): acceptance is always individual, never
    representative of the whole vendor organization - a new collaborator
    never inherits another collaborator's acceptance."""

    id: str
    tenant_id: str
    user_id: str
    membership_id: str
    type: AgreementType
    version: str
    ip: str
    user_agent: str | None
    accepted_at: datetime

    @staticmethod
    def create(
        *,
        tenant_id: str,
        user_id: str,
        membership_id: str,
        type: AgreementType,
        version: str,
        ip: str,
        user_agent: str | None,
    ) -> "Agreement":
        return Agreement(
            id=new_id(),
            tenant_id=tenant_id,
            user_id=user_id,
            membership_id=membership_id,
            type=type,
            version=version,
            ip=ip,
            user_agent=user_agent,
            accepted_at=datetime.now(UTC),
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "membership_id": self.membership_id,
            "type": self.type,
            "version": self.version,
            "ip": self.ip,
            "user_agent": self.user_agent,
            "accepted_at": self.accepted_at,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "Agreement":
        return Agreement(
            id=doc["_id"],
            tenant_id=doc["tenant_id"],
            user_id=doc["user_id"],
            membership_id=doc["membership_id"],
            type=doc["type"],
            version=doc["version"],
            ip=doc["ip"],
            user_agent=doc.get("user_agent"),
            accepted_at=doc["accepted_at"],
        )
