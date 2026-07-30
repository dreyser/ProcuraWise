from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from procurawise.evaluations.models import Dimension

AssignmentStatus = Literal["not_started", "in_progress", "completed"]


def new_id() -> str:
    return uuid4().hex


@dataclass(frozen=True)
class Assignment:
    """Binds one evaluator Membership to one section (spec §16: "Sección/
    evaluador, fecha y progreso") within a single dimension of an Evaluation.

    This is a finer-grained concern than the evaluator_functional/technical/
    economic role split (Fase 9 Block 1): the role says which *dimension* an
    evaluator may ever be assigned to at all; `section` (Requirement.category
    values within that dimension) says which specific part of it this
    particular evaluator is currently responsible for, and `status` tracks
    their progress (spec §6.7: "Asignar secciones completas a evaluadores").
    """

    id: str
    tenant_id: str
    evaluation_id: str
    dimension: Dimension
    section: str
    evaluator_membership_id: str
    assigned_by_membership_id: str
    status: AssignmentStatus
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def create(
        tenant_id: str,
        evaluation_id: str,
        dimension: Dimension,
        section: str,
        evaluator_membership_id: str,
        assigned_by_membership_id: str,
    ) -> "Assignment":
        now = datetime.now(UTC)
        return Assignment(
            id=new_id(),
            tenant_id=tenant_id,
            evaluation_id=evaluation_id,
            dimension=dimension,
            section=section,
            evaluator_membership_id=evaluator_membership_id,
            assigned_by_membership_id=assigned_by_membership_id,
            status="not_started",
            created_at=now,
            updated_at=now,
        )

    def with_status(self, status: AssignmentStatus) -> "Assignment":
        return replace(self, status=status, updated_at=datetime.now(UTC))

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "tenant_id": self.tenant_id,
            "evaluation_id": self.evaluation_id,
            "dimension": self.dimension,
            "section": self.section,
            "evaluator_membership_id": self.evaluator_membership_id,
            "assigned_by_membership_id": self.assigned_by_membership_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "Assignment":
        return Assignment(
            id=doc["_id"],
            tenant_id=doc["tenant_id"],
            evaluation_id=doc["evaluation_id"],
            dimension=doc["dimension"],
            section=doc["section"],
            evaluator_membership_id=doc["evaluator_membership_id"],
            assigned_by_membership_id=doc["assigned_by_membership_id"],
            status=doc["status"],
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )
