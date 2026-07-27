from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

EvaluationStatus = Literal["draft", "collecting_responses", "evaluating", "completed"]
Dimension = Literal["functional", "technical"]
Priority = Literal["mandatory", "important", "desirable"]
ResponseType = Literal[
    "compliant_status",
    "text",
    "single_choice",
    "multi_choice",
    "number",
    "percentage",
    "date",
    "url",
    "comment",
    "currency",
]

# Global product weights (PRD §7.1): functional 40%, technical 20%, economic 40%
# of a 100-point model. VS-2B only implements functional+technical - requirement
# weights within a dimension are expressed directly on this global scale (they
# must sum to exactly the dimension's allocation), not renormalized to 100 each.
DIMENSION_MAX_POINTS: dict[Dimension, float] = {"functional": 40.0, "technical": 20.0}
ECONOMIC_MAX_POINTS = 40.0
PARTIAL_RESULT_MAX_POINTS = sum(DIMENSION_MAX_POINTS.values())  # 60 - functional+technical only

MAX_LINKED_VENDORS = 6


def new_id() -> str:
    return uuid4().hex


@dataclass(frozen=True)
class Requirement:
    """Embedded in Evaluation.requirements. `required` (must the vendor answer
    before submit) is independent of `priority == "mandatory"` (generates a
    non-blocking alert in results when scored low) - two distinct concepts
    from PRD §6.3, not one field wearing two hats."""

    id: str
    dimension: Dimension
    category: str
    title: str
    description: str
    priority: Priority
    response_type: ResponseType
    weight: float
    required: bool
    buyer_guidance: str | None
    display_order: int
    options: list[str] | None
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def create(
        dimension: Dimension,
        category: str,
        title: str,
        description: str,
        priority: Priority,
        response_type: ResponseType,
        weight: float,
        required: bool,
        display_order: int,
        buyer_guidance: str | None = None,
        options: list[str] | None = None,
    ) -> "Requirement":
        if response_type in ("single_choice", "multi_choice") and not options:
            raise ValueError(f"response_type={response_type!r} requires non-empty options")
        now = datetime.now(UTC)
        return Requirement(
            id=new_id(),
            dimension=dimension,
            category=category,
            title=title,
            description=description,
            priority=priority,
            response_type=response_type,
            weight=weight,
            required=required,
            buyer_guidance=buyer_guidance,
            display_order=display_order,
            options=options,
            created_at=now,
            updated_at=now,
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "dimension": self.dimension,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "response_type": self.response_type,
            "weight": self.weight,
            "required": self.required,
            "buyer_guidance": self.buyer_guidance,
            "display_order": self.display_order,
            "options": self.options,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "Requirement":
        return Requirement(
            id=doc["id"],
            dimension=doc["dimension"],
            category=doc["category"],
            title=doc["title"],
            description=doc["description"],
            priority=doc["priority"],
            response_type=doc["response_type"],
            weight=doc["weight"],
            required=doc["required"],
            buyer_guidance=doc.get("buyer_guidance"),
            display_order=doc["display_order"],
            options=doc.get("options"),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )


@dataclass(frozen=True)
class Evaluation:
    """`linked_vendor_count` is an atomic reservation counter (see
    evaluations.repository.reserve_vendor_slot) enforcing the 6-vendor cap
    under concurrent linking - it is not derived by counting Proposal
    documents on every read. `Proposal` is the sole representation of the
    Evaluation<->VendorOrganization association; there is no separate
    evaluation_vendors collection."""

    id: str
    tenant_id: str
    name: str
    description: str
    status: EvaluationStatus
    requirements: list[Requirement]
    linked_vendor_count: int
    created_by_membership_id: str
    created_at: datetime
    updated_at: datetime
    collecting_responses_started_at: datetime | None
    evaluating_started_at: datetime | None
    completed_at: datetime | None

    @staticmethod
    def create(
        tenant_id: str, name: str, description: str, created_by_membership_id: str
    ) -> "Evaluation":
        now = datetime.now(UTC)
        return Evaluation(
            id=new_id(),
            tenant_id=tenant_id,
            name=name,
            description=description,
            status="draft",
            requirements=[],
            linked_vendor_count=0,
            created_by_membership_id=created_by_membership_id,
            created_at=now,
            updated_at=now,
            collecting_responses_started_at=None,
            evaluating_started_at=None,
            completed_at=None,
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "requirements": [r.to_document() for r in self.requirements],
            "linked_vendor_count": self.linked_vendor_count,
            "created_by_membership_id": self.created_by_membership_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "collecting_responses_started_at": self.collecting_responses_started_at,
            "evaluating_started_at": self.evaluating_started_at,
            "completed_at": self.completed_at,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "Evaluation":
        return Evaluation(
            id=doc["_id"],
            tenant_id=doc["tenant_id"],
            name=doc["name"],
            description=doc["description"],
            status=doc["status"],
            requirements=[Requirement.from_document(r) for r in doc.get("requirements", [])],
            linked_vendor_count=doc.get("linked_vendor_count", 0),
            created_by_membership_id=doc["created_by_membership_id"],
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
            collecting_responses_started_at=doc.get("collecting_responses_started_at"),
            evaluating_started_at=doc.get("evaluating_started_at"),
            completed_at=doc.get("completed_at"),
        )
