from datetime import datetime

from procurawise.qna.models import AnswerVisibility, QuestionScope, QuestionStatus
from procurawise.shared.api_models import APIModel


class QuestionCreateRequest(APIModel):
    scope: QuestionScope
    requirement_id: str | None = None
    body: str


# Named distinctly from vendor_portal.schemas.AnswerWriteRequest (the
# proposal-answer request) - both existing under the same OpenAPI component-
# schema namespace would collide and force orval to auto-prefix both with
# their full module path.
class PublishAnswerRequest(APIModel):
    body: str
    visibility: AnswerVisibility
    expected_version: int


class AnswerVersionResponse(APIModel):
    version: int
    body: str
    visibility: AnswerVisibility
    answered_by_membership_id: str
    answered_at: datetime


# The vendor's own view of its own question - identity fields are trivially
# "visible" here since the caller *is* that identity; this schema is never
# reused for a cross-vendor read (see PublicQuestionResponse).
class VendorQuestionResponse(APIModel):
    id: str
    proposal_id: str
    requirement_id: str | None
    scope: QuestionScope
    body: str
    status: QuestionStatus
    version: int
    created_at: datetime
    current_answer: AnswerVersionResponse | None
    answer_history: list[AnswerVersionResponse]


class VendorQuestionListResponse(APIModel):
    items: list[VendorQuestionResponse]


# Fase 17 planning §6.B/§8 R1 (binary visibility, no "public with identity"
# state): the cross-vendor projection of a published_anonymized question -
# structurally, not just by convention, omits vendor_org_id/vendor_org_name/
# created_by_membership_id. Never share a field list with
# VendorQuestionResponse/BuyerQuestionResponse - adding an identity field to
# either of those must never silently leak into this one.
class PublicQuestionResponse(APIModel):
    id: str
    requirement_id: str | None
    scope: QuestionScope
    body: str
    current_answer: AnswerVersionResponse | None


class PublicQuestionListResponse(APIModel):
    items: list[PublicQuestionResponse]


# The buyer's view - real vendor identity always included, regardless of the
# answer's own visibility (visibility only governs what *other vendors* see).
class BuyerQuestionResponse(APIModel):
    id: str
    proposal_id: str
    vendor_org_id: str
    requirement_id: str | None
    scope: QuestionScope
    body: str
    status: QuestionStatus
    version: int
    created_by_membership_id: str
    created_at: datetime
    current_answer: AnswerVersionResponse | None
    answer_history: list[AnswerVersionResponse]


class BuyerQuestionListResponse(APIModel):
    items: list[BuyerQuestionResponse]
