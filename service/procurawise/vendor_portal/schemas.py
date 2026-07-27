from datetime import datetime
from typing import Any

from procurawise.evaluations.models import Dimension, Priority, ResponseType
from procurawise.proposals.models import ProposalStatus
from procurawise.shared.api_models import APIModel


class AnswerWriteRequest(APIModel):
    """`expected_version` is the optimistic-concurrency contract (plan §12):
    the version the vendor last read. A mismatch means someone/something
    changed the proposal concurrently - the server responds 409 rather than
    accepting the write."""

    value: Any
    vendor_comment: str | None = None
    expected_version: int


class SubmitRequest(APIModel):
    expected_version: int


class VendorRequirementResponse(APIModel):
    """Deliberately narrower than evaluations.schemas.RequirementResponse:
    no `weight` field - scoring weight is buyer-internal configuration, not
    exposed to the vendor portal (CLAUDE.md: comentarios internos/scoring
    nunca visibles al proveedor)."""

    id: str
    dimension: Dimension
    category: str
    title: str
    description: str
    priority: Priority
    response_type: ResponseType
    required: bool
    buyer_guidance: str | None
    display_order: int
    options: list[str] | None


class VendorAnswerResponse(APIModel):
    requirement_id: str
    value: Any
    vendor_comment: str | None
    updated_at: datetime


class VendorProposalSummaryResponse(APIModel):
    id: str
    evaluation_id: str
    evaluation_name: str
    status: ProposalStatus
    version: int
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None


class VendorProposalDetailResponse(APIModel):
    id: str
    evaluation_id: str
    evaluation_name: str
    status: ProposalStatus
    version: int
    requirements: list[VendorRequirementResponse]
    answers: list[VendorAnswerResponse]
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
