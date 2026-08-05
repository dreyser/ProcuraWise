from datetime import datetime
from decimal import Decimal
from typing import Any

from procurawise.evaluations.schemas import RequirementResponse
from procurawise.proposals.models import ProposalAnswerVersionStatus, ProposalStatus
from procurawise.shared.api_models import APIModel
from procurawise.tco.models import CostCategory, CostItemVersionStatus, CostType, Currency
from procurawise.tco.schemas import TcoResultResponse


class AnswerResponse(APIModel):
    requirement_id: str
    value: Any
    vendor_comment: str | None
    updated_at: datetime
    status: ProposalAnswerVersionStatus
    source_proposal_version: int | None


class SnapshotCostItemResponse(APIModel):
    """Fase 21 - the frozen CostItem shape read back from
    `ProposalSnapshot.cost_items` for the round comparison view (plan §12.7,
    R10). Distinct from vendor_portal's own CostItemResponse (same field
    shape, different bounded context/OpenAPI component name)."""

    id: str
    concept: str
    category: CostCategory
    description: str | None
    billing_unit: str
    quantity: Decimal
    unit_price: Decimal
    currency: Currency
    frequency_per_year: Decimal
    tax_pct: Decimal
    discount_pct: Decimal
    year_start: int
    year_end: int
    annual_increment_pct: Decimal
    mandatory: bool
    cost_type: CostType
    notes: str | None
    created_at: datetime
    updated_at: datetime
    status: CostItemVersionStatus
    source_proposal_version: int | None


class SnapshotResponse(APIModel):
    snapshot_id: str
    taken_at: datetime
    evaluation_id: str
    evaluation_name: str
    vendor_org_id: str
    vendor_org_name: str
    requirements: list[RequirementResponse]
    answers: list[AnswerResponse]
    submitted_by_membership_id: str
    submitted_at: datetime
    document_ids: list[str]
    round: int
    # Fase 21 (ADR 0013, plan R10) - frozen cost items + TCO for this exact
    # round, needed to compare Ronda 0 vs Ronda 1 without a dedicated diff
    # endpoint. `None` for tco_result on any snapshot taken before Fase 19.
    cost_items: list[SnapshotCostItemResponse]
    tco_result: TcoResultResponse | None


class ProposalSummaryResponse(APIModel):
    id: str
    evaluation_id: str
    vendor_org_id: str
    status: ProposalStatus
    version: int
    round: int
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None


class ReopenProposalRequest(APIModel):
    """Fase 21 (FR-047: "Sólo el dueño; motivo, nueva fecha y auditoría").
    `reason` is required (never an empty/whitespace-only string, validated
    in the service layer) and is persisted on the Proposal itself (visible
    to the reopened vendor), not just audited - same transparency
    precedent as Evaluation.approval_comment."""

    reason: str
    response_deadline: datetime


class ProposalDetailResponse(APIModel):
    id: str
    evaluation_id: str
    vendor_org_id: str
    status: ProposalStatus
    version: int
    round: int
    answers: list[AnswerResponse]
    # Fase 21 (ADR 0013) - full history, one entry per round (max 2 in the
    # MVP), oldest first. The client reads `snapshots[-1]` for "current" -
    # no separate endpoint/field for the comparison view (plan R10).
    snapshots: list[SnapshotResponse]
    reopened_reason: str | None
    reopened_at: datetime | None
    reopened_by_membership_id: str | None
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
