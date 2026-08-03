from datetime import datetime
from typing import Any

from procurawise.evaluations.schemas import RequirementResponse
from procurawise.proposals.models import ProposalStatus
from procurawise.shared.api_models import APIModel


class AnswerResponse(APIModel):
    requirement_id: str
    value: Any
    vendor_comment: str | None
    updated_at: datetime


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


class ProposalSummaryResponse(APIModel):
    id: str
    evaluation_id: str
    vendor_org_id: str
    status: ProposalStatus
    version: int
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None


class ProposalDetailResponse(APIModel):
    id: str
    evaluation_id: str
    vendor_org_id: str
    status: ProposalStatus
    version: int
    answers: list[AnswerResponse]
    snapshot: SnapshotResponse | None
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
