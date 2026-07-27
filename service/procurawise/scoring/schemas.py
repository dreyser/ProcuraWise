from datetime import datetime
from typing import Literal

from procurawise.evaluations.models import Dimension
from procurawise.shared.api_models import APIModel


class ScoreWriteRequest(APIModel):
    """`version` is intentionally part of the write contract (optimistic
    concurrency), not a server-managed field being smuggled in - omit/None
    on first create for a given requirement, echo the current Score.version
    on every subsequent update."""

    score: int
    comment: str | None = None
    version: int | None = None


class ScoreResponse(APIModel):
    id: str
    requirement_id: str
    dimension: Dimension
    priority: str
    requirement_weight: float
    score: int
    comment: str | None
    weighted_points: float
    mandatory_alert: bool
    version: int
    created_by_membership_id: str
    updated_by_membership_id: str
    created_at: datetime
    updated_at: datetime


class DimensionSubtotal(APIModel):
    earned_points: float
    maximum_points: float


class EconomicSubtotal(APIModel):
    status: Literal["not_available", "available"]
    earned_points: float | None
    maximum_points: float


class PartialResult(APIModel):
    earned_points: float
    maximum_points: float
    model_coverage_percent: float


class RequirementScoreDetail(APIModel):
    requirement_id: str
    dimension: Dimension
    title: str
    priority: str
    raw_score: int
    requirement_weight: float
    weighted_points: float
    evaluator_membership_id: str
    mandatory_alert: bool


class ProposalResult(APIModel):
    """functional/technical/economic/partial_result are per-proposal, not a
    single evaluation-wide aggregate: each vendor's Proposal is scored
    independently (Score's natural key includes proposal_id), so summing
    weighted_points across competing proposals into one number would not be
    mathematically meaningful. Nothing here ranks or compares proposals -
    each subtotal stands on its own; the reader compares them, the system
    does not (no automatic adjudication)."""

    proposal_id: str
    vendor_org_id: str
    vendor_org_name: str
    status: Literal["submitted"]
    functional: DimensionSubtotal
    technical: DimensionSubtotal
    economic: EconomicSubtotal
    partial_result: PartialResult
    scores: list[RequirementScoreDetail]
    mandatory_alerts_count: int


class DraftProposalSummary(APIModel):
    proposal_id: str
    vendor_org_id: str
    vendor_org_name: str


class ResultsResponse(APIModel):
    result_status: Literal["partial"]
    is_final: bool
    scoring_status: Literal["incomplete", "complete"]
    proposals: list[ProposalResult]
    draft_proposals: list[DraftProposalSummary]
    disclaimer: str
