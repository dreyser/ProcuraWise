from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from procurawise.evaluations.models import Dimension


def new_id() -> str:
    return uuid4().hex


@dataclass(frozen=True)
class Score:
    """One canonical score per (evaluation_id, proposal_id, snapshot_id,
    requirement_id) - see plan §3/P1. No per-evaluator scores, no
    averaging/consensus: any evaluation_owner/evaluator may create or
    overwrite it, `version` protects concurrent writes (409 on stale
    version), and created_by/updated_by_membership_id record attribution."""

    id: str
    tenant_id: str
    evaluation_id: str
    proposal_id: str
    snapshot_id: str
    requirement_id: str
    dimension: Dimension
    priority: str
    requirement_weight: float
    score: int
    comment: str | None
    version: int
    created_by_membership_id: str
    updated_by_membership_id: str
    created_at: datetime
    updated_at: datetime
    # Fase 18 (evaluacion asistida por IA, ADR 0022): set only when this
    # write's ScoreWriteRequest referenced an AIExecution's suggestion -
    # None for every purely-manual score, past and future. Never written by
    # `ai/` itself: the evaluator's own PUT request carries this id, same as
    # any other field on ScoreWriteRequest (plan §1/§11 - "aceptar o
    # modificar" is not a new write path).
    source_ai_execution_id: str | None

    @staticmethod
    def create(
        tenant_id: str,
        evaluation_id: str,
        proposal_id: str,
        snapshot_id: str,
        requirement_id: str,
        dimension: Dimension,
        priority: str,
        requirement_weight: float,
        score: int,
        comment: str | None,
        membership_id: str,
        source_ai_execution_id: str | None = None,
    ) -> "Score":
        now = datetime.now(UTC)
        return Score(
            id=new_id(),
            tenant_id=tenant_id,
            evaluation_id=evaluation_id,
            proposal_id=proposal_id,
            snapshot_id=snapshot_id,
            requirement_id=requirement_id,
            dimension=dimension,
            priority=priority,
            requirement_weight=requirement_weight,
            score=score,
            comment=comment,
            version=1,
            created_by_membership_id=membership_id,
            updated_by_membership_id=membership_id,
            created_at=now,
            updated_at=now,
            source_ai_execution_id=source_ai_execution_id,
        )

    @property
    def weighted_points(self) -> float:
        return round((self.score / 5) * self.requirement_weight, 2)

    @property
    def mandatory_alert(self) -> bool:
        return self.priority == "mandatory" and self.score < 5

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "tenant_id": self.tenant_id,
            "evaluation_id": self.evaluation_id,
            "proposal_id": self.proposal_id,
            "snapshot_id": self.snapshot_id,
            "requirement_id": self.requirement_id,
            "dimension": self.dimension,
            "priority": self.priority,
            "requirement_weight": self.requirement_weight,
            "score": self.score,
            "comment": self.comment,
            "version": self.version,
            "created_by_membership_id": self.created_by_membership_id,
            "updated_by_membership_id": self.updated_by_membership_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source_ai_execution_id": self.source_ai_execution_id,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "Score":
        return Score(
            id=doc["_id"],
            tenant_id=doc["tenant_id"],
            evaluation_id=doc["evaluation_id"],
            proposal_id=doc["proposal_id"],
            snapshot_id=doc["snapshot_id"],
            requirement_id=doc["requirement_id"],
            dimension=doc["dimension"],
            priority=doc["priority"],
            requirement_weight=doc["requirement_weight"],
            score=doc["score"],
            comment=doc.get("comment"),
            version=doc["version"],
            created_by_membership_id=doc["created_by_membership_id"],
            updated_by_membership_id=doc["updated_by_membership_id"],
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
            source_ai_execution_id=doc.get("source_ai_execution_id"),
        )
