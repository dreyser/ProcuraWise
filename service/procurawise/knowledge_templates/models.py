from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from procurawise.evaluations.models import Requirement


def new_id() -> str:
    return uuid4().hex


@dataclass(frozen=True)
class KnowledgeTemplate:
    """Fase 11 (biblioteca de requerimientos, sin IA): a named, reusable set
    of Requirement-shaped items an evaluation_owner can apply to a draft
    Evaluation to reduce manual entry. `items` reuses `Requirement` verbatim
    (evaluations.models) - it is already a self-contained value object with
    no evaluation-specific field, so no separate "template item" shape is
    needed. `weight` is kept on items (not stripped) so applying a template
    produces an immediately usable starting point."""

    id: str
    tenant_id: str
    name: str
    description: str
    items: list[Requirement]
    created_by_membership_id: str
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def create(
        tenant_id: str,
        name: str,
        description: str,
        created_by_membership_id: str,
    ) -> "KnowledgeTemplate":
        now = datetime.now(UTC)
        return KnowledgeTemplate(
            id=new_id(),
            tenant_id=tenant_id,
            name=name,
            description=description,
            items=[],
            created_by_membership_id=created_by_membership_id,
            created_at=now,
            updated_at=now,
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "description": self.description,
            "items": [item.to_document() for item in self.items],
            "created_by_membership_id": self.created_by_membership_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "KnowledgeTemplate":
        return KnowledgeTemplate(
            id=doc["_id"],
            tenant_id=doc["tenant_id"],
            name=doc["name"],
            description=doc["description"],
            items=[Requirement.from_document(item) for item in doc.get("items", [])],
            created_by_membership_id=doc["created_by_membership_id"],
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )
