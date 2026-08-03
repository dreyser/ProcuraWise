from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

QuestionScope = Literal["requirement", "general"]
QuestionStatus = Literal["open", "answered", "withdrawn"]
# Binary by design (Fase 17 planning §8/§B): three independent, consistent
# sources (backlog.md, spec §6.6, spec §26 DoD) all describe exactly two
# visibility outcomes - there is no third "public with vendor identity
# revealed" state anywhere in the governing documents. "private" is visible
# only to the asking vendor_org and the buyer; "published_anonymized" is
# visible to every vendor_org in the evaluation, with the asking vendor's
# identity never included in the schema served to anyone but the buyer.
AnswerVisibility = Literal["private", "published_anonymized"]


def new_id() -> str:
    return uuid4().hex


@dataclass(frozen=True)
class AnswerVersion:
    """One immutable answer draft/publication (Fase 17 planning §6.B/§14):
    publishing an edit never overwrites a prior version - spec §6.6 states
    a published answer "queda versionada". `visibility` is decided in the
    same act as answering (no separate publish step, §6.B Q22-23), so every
    version - including the very first - already carries its own
    visibility."""

    version: int
    body: str
    visibility: AnswerVisibility
    answered_by_membership_id: str
    answered_at: datetime

    def to_document(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "body": self.body,
            "visibility": self.visibility,
            "answered_by_membership_id": self.answered_by_membership_id,
            "answered_at": self.answered_at,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "AnswerVersion":
        return AnswerVersion(
            version=doc["version"],
            body=doc["body"],
            visibility=doc["visibility"],
            answered_by_membership_id=doc["answered_by_membership_id"],
            answered_at=doc["answered_at"],
        )


@dataclass(frozen=True)
class Question:
    """One vendor-authored question, tied to a specific Requirement or
    general (Fase 17 planning §D, grain R5: one `qna_questions` document per
    question, answer(s) embedded rather than a separate collection - same
    reasoning as Proposal embedding ProposalAnswer). `version` is optimistic
    concurrency over the whole document (same pattern as Proposal.version),
    not per-answer. `current_answer` is the live, further-editable answer;
    republishing moves the previous `current_answer` into `answer_history`
    (frozen, never mutated) before installing the new one - only the
    identity of `vendor_org_id`/`created_by_membership_id` is ever withheld
    from other vendors' view, and only as a response-schema projection
    (never a transformation of what is persisted here, planning §D Q56)."""

    id: str
    tenant_id: str
    evaluation_id: str
    proposal_id: str
    vendor_org_id: str
    requirement_id: str | None
    scope: QuestionScope
    body: str
    status: QuestionStatus
    version: int
    created_by_membership_id: str
    created_at: datetime
    current_answer: AnswerVersion | None
    answer_history: list[AnswerVersion]

    @staticmethod
    def create(
        *,
        tenant_id: str,
        evaluation_id: str,
        proposal_id: str,
        vendor_org_id: str,
        requirement_id: str | None,
        scope: QuestionScope,
        body: str,
        created_by_membership_id: str,
    ) -> "Question":
        return Question(
            id=new_id(),
            tenant_id=tenant_id,
            evaluation_id=evaluation_id,
            proposal_id=proposal_id,
            vendor_org_id=vendor_org_id,
            requirement_id=requirement_id,
            scope=scope,
            body=body,
            status="open",
            version=1,
            created_by_membership_id=created_by_membership_id,
            created_at=datetime.now(UTC),
            current_answer=None,
            answer_history=[],
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "tenant_id": self.tenant_id,
            "evaluation_id": self.evaluation_id,
            "proposal_id": self.proposal_id,
            "vendor_org_id": self.vendor_org_id,
            "requirement_id": self.requirement_id,
            "scope": self.scope,
            "body": self.body,
            "status": self.status,
            "version": self.version,
            "created_by_membership_id": self.created_by_membership_id,
            "created_at": self.created_at,
            "current_answer": self.current_answer.to_document() if self.current_answer else None,
            "answer_history": [a.to_document() for a in self.answer_history],
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "Question":
        current_answer_doc = doc.get("current_answer")
        return Question(
            id=doc["_id"],
            tenant_id=doc["tenant_id"],
            evaluation_id=doc["evaluation_id"],
            proposal_id=doc["proposal_id"],
            vendor_org_id=doc["vendor_org_id"],
            requirement_id=doc.get("requirement_id"),
            scope=doc["scope"],
            body=doc["body"],
            status=doc["status"],
            version=doc["version"],
            created_by_membership_id=doc["created_by_membership_id"],
            created_at=doc["created_at"],
            current_answer=AnswerVersion.from_document(current_answer_doc)
            if current_answer_doc
            else None,
            answer_history=[AnswerVersion.from_document(a) for a in doc.get("answer_history", [])],
        )
