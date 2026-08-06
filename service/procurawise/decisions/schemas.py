from datetime import datetime
from typing import Any

from procurawise.decisions.models import DecisionOutcome, DecisionStatus
from procurawise.shared.api_models import APIModel


class DecisionUpdateRequest(APIModel):
    """Partial update (exclude_unset, same convention as
    evaluations.schemas.RequirementUpdateRequest) - only the fields the
    caller actually sends are considered "set"; the service merges them with
    the current Decision before validating the resultant selection as one
    consistent unit."""

    outcome: DecisionOutcome | None = None
    selected_vendor_org_id: str | None = None
    void_reason: str | None = None
    justification: str | None = None


class SetDecisionApproverRequest(APIModel):
    approver_membership_id: str


class DecisionApprovalRequest(APIModel):
    comment: str | None = None


class DecisionRejectionRequest(APIModel):
    comment: str


class DecisionResponse(APIModel):
    id: str
    evaluation_id: str
    status: DecisionStatus
    outcome: DecisionOutcome | None
    selected_vendor_org_id: str | None
    selected_proposal_id: str | None
    selected_proposal_snapshot_id: str | None
    void_reason: str | None
    justification: str | None
    approver_membership_id: str | None
    created_by_membership_id: str
    created_at: datetime
    updated_at: datetime
    approval_requested_at: datetime | None
    approval_requested_by_membership_id: str | None
    approval_decided_at: datetime | None
    approval_decided_by_membership_id: str | None
    approval_comment: str | None
    decision_snapshot_id: str | None


class DecisionReadinessResponse(APIModel):
    evaluation_completed: bool
    decision_exists: bool
    decision_status: DecisionStatus | None
    can_create: bool
    can_edit: bool
    can_request_approval: bool
    request_approval_reasons: list[str]
    can_approve_or_reject: bool
    suggested_approver_membership_id: str | None


class DecisionSnapshotResponse(APIModel):
    snapshot_id: str
    evaluation_id: str
    outcome: DecisionOutcome
    selected_vendor_org_id: str | None
    selected_vendor_org_name: str | None
    selected_proposal_id: str | None
    selected_proposal_snapshot_id: str | None
    void_reason: str | None
    justification: str
    approver_membership_id: str
    decided_at: datetime
    decided_by_membership_id: str
    proposal_results: list[dict[str, Any]]
    taken_at: datetime
