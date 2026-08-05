from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from procurawise.evaluations.models import Requirement
from procurawise.tco.models import CostItem, TcoResult

ProposalStatus = Literal["draft", "submitted"]

# Fase 21 (ADR 0013): a ProposalAnswer always maps 1:1 to a fixed
# Requirement (Requirements are draft-only, never edited during a
# negotiation round), so unlike CostItem it never has a "removed" status -
# clearing an answer's value is represented as value=None with
# status="modified", not a third state. "inherited" is set only by
# ProposalService.reopen() when copying the previous round's answers
# forward; it flips to "modified" the moment the vendor edits it again
# (proposals.service.update_answer).
ProposalAnswerVersionStatus = Literal["inherited", "modified"]


def new_id() -> str:
    return uuid4().hex


@dataclass(frozen=True)
class ProposalAnswer:
    """`value` shape depends on the frozen Requirement's response_type (see
    proposals.service answer validators) - stored as whatever JSON-safe
    structure that type dictates (str, float, bool, list[str], or the
    {amount, currency_code} dict for `currency`)."""

    requirement_id: str
    value: Any
    vendor_comment: str | None
    updated_at: datetime
    # Fase 21 (ADR 0013): "modified" is the correct default for every
    # Ronda-0-authored answer (nothing to inherit from yet).
    # `source_proposal_version` stays None until ProposalService.reopen()
    # copies this exact answer forward as "inherited".
    status: ProposalAnswerVersionStatus = "modified"
    source_proposal_version: int | None = None

    def to_document(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "value": self.value,
            "vendor_comment": self.vendor_comment,
            "updated_at": self.updated_at,
            "status": self.status,
            "source_proposal_version": self.source_proposal_version,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "ProposalAnswer":
        return ProposalAnswer(
            requirement_id=doc["requirement_id"],
            value=doc.get("value"),
            vendor_comment=doc.get("vendor_comment"),
            updated_at=doc["updated_at"],
            status=doc.get("status", "modified"),
            source_proposal_version=doc.get("source_proposal_version"),
        )


@dataclass(frozen=True)
class ProposalSnapshot:
    """Frozen at submit time (Proposal.status draft->submitted). Requirements
    are a deep copy (Requirement dataclass shape) taken at the moment of
    submission - Score always references snapshot_id, never the live,
    mutable Evaluation."""

    snapshot_id: str
    taken_at: datetime
    evaluation_id: str
    evaluation_name: str
    vendor_org_id: str
    vendor_org_name: str
    requirements: list[Requirement]
    answers: list[ProposalAnswer]
    submitted_by_membership_id: str
    submitted_at: datetime
    # Fase 16 (documents): ids of every Document with status="current" for
    # this proposal at the moment of submission - the Document rows
    # themselves (not a copy of their metadata) remain the source of truth,
    # same reasoning as `requirements`/`answers` already living as full
    # copies here rather than as bare ids: this list is the copy needed to
    # answer "what was submitted", the rows behind each id are still fetched
    # live. Absent (`doc.get`) on any snapshot taken before this field
    # existed - an empty list is the correct, honest answer for those.
    document_ids: list[str]
    # Fase 19 (ADR 0008, plan §11.1): full copy of the CostItems submitted,
    # plus the deterministic TcoResult computed from them and the FX rate(s)
    # resolved at this exact moment - never recomputed later, same
    # "requirements"/"answers" freeze-at-submit reasoning above. `None` on
    # any snapshot taken before this field existed.
    cost_items: list[CostItem]
    tco_result: TcoResult | None
    # Fase 21 (ADR 0013): 0 for the initial proposal, 1 for the single
    # negotiation round the MVP allows (see Proposal.round). Defaults to 0
    # for every snapshot taken before this field existed - all of those were
    # necessarily the (only) initial submission.
    round: int = 0

    def to_document(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "taken_at": self.taken_at,
            "evaluation_id": self.evaluation_id,
            "evaluation_name": self.evaluation_name,
            "vendor_org_id": self.vendor_org_id,
            "vendor_org_name": self.vendor_org_name,
            "requirements": [r.to_document() for r in self.requirements],
            "answers": [a.to_document() for a in self.answers],
            "submitted_by_membership_id": self.submitted_by_membership_id,
            "submitted_at": self.submitted_at,
            "document_ids": self.document_ids,
            "cost_items": [c.to_document() for c in self.cost_items],
            "tco_result": self.tco_result.to_document() if self.tco_result else None,
            "round": self.round,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "ProposalSnapshot":
        tco_result_doc = doc.get("tco_result")
        return ProposalSnapshot(
            snapshot_id=doc["snapshot_id"],
            taken_at=doc["taken_at"],
            evaluation_id=doc["evaluation_id"],
            evaluation_name=doc["evaluation_name"],
            vendor_org_id=doc["vendor_org_id"],
            vendor_org_name=doc["vendor_org_name"],
            requirements=[Requirement.from_document(r) for r in doc.get("requirements", [])],
            answers=[ProposalAnswer.from_document(a) for a in doc.get("answers", [])],
            submitted_by_membership_id=doc["submitted_by_membership_id"],
            submitted_at=doc["submitted_at"],
            document_ids=doc.get("document_ids", []),
            cost_items=[CostItem.from_document(c) for c in doc.get("cost_items", [])],
            tco_result=TcoResult.from_document(tco_result_doc) if tco_result_doc else None,
            round=doc.get("round", 0),
        )


@dataclass(frozen=True)
class Proposal:
    """The sole representation of the Evaluation<->VendorOrganization
    association (see evaluations.models.Evaluation docstring) - created
    directly when a vendor is linked, not as a side effect of a separate
    association document, and never re-created for a negotiation round
    (plan Fase 21 §9/B21-23: ADR 0013's versioning lives inside this same
    document, as a growing `snapshots` history, not as a new Proposal per
    round). `version` is optimistic concurrency: every answer edit and
    submit must supply the version they read, or the write is rejected with
    409 rather than silently overwriting a concurrent change or freezing a
    stale snapshot. `version` is deliberately NOT the negotiation round
    counter - it increments on every single answer/cost-item edit, not just
    on submit (see proposals.repository) - `round` below is the separate,
    coarser counter ADR 0013 actually needs."""

    id: str
    tenant_id: str
    evaluation_id: str
    vendor_org_id: str
    status: ProposalStatus
    version: int
    # Fase 21 (ADR 0013): 0 = initial proposal (Ronda 0), 1 = the single
    # negotiation round the MVP allows (Ronda 1/BAFO). Incremented only by
    # ProposalService.reopen(), never by an ordinary answer/cost-item edit.
    round: int
    answers: list[ProposalAnswer]
    # Fase 19: vendor-authored cost lines, same lifecycle as `answers`
    # (draft-editable, frozen into the current snapshot's cost_items at
    # submit).
    cost_items: list[CostItem]
    # Fase 21: append-only history of every submitted snapshot, one per
    # round (max 2 in the MVP - see ProposalService.reopen's cap). Replaces
    # the pre-Fase-21 single `snapshot` slot; `current_snapshot` below is
    # the direct replacement for every old `proposal.snapshot` read site.
    snapshots: list[ProposalSnapshot]
    # Fase 21 (FR-047): set only by reopen() - persisted (not just audited)
    # so the reopened vendor can see why, mirroring how
    # Evaluation.approval_comment already persists a human-readable reason
    # rather than burying it only in the audit trail.
    reopened_reason: str | None
    reopened_at: datetime | None
    reopened_by_membership_id: str | None
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None

    @property
    def current_snapshot(self) -> ProposalSnapshot | None:
        return self.snapshots[-1] if self.snapshots else None

    @staticmethod
    def create(tenant_id: str, evaluation_id: str, vendor_org_id: str) -> "Proposal":
        now = datetime.now(UTC)
        return Proposal(
            id=new_id(),
            tenant_id=tenant_id,
            evaluation_id=evaluation_id,
            vendor_org_id=vendor_org_id,
            status="draft",
            version=1,
            round=0,
            answers=[],
            cost_items=[],
            snapshots=[],
            reopened_reason=None,
            reopened_at=None,
            reopened_by_membership_id=None,
            created_at=now,
            updated_at=now,
            submitted_at=None,
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "tenant_id": self.tenant_id,
            "evaluation_id": self.evaluation_id,
            "vendor_org_id": self.vendor_org_id,
            "status": self.status,
            "version": self.version,
            "round": self.round,
            "answers": [a.to_document() for a in self.answers],
            "cost_items": [c.to_document() for c in self.cost_items],
            "snapshots": [s.to_document() for s in self.snapshots],
            "reopened_reason": self.reopened_reason,
            "reopened_at": self.reopened_at,
            "reopened_by_membership_id": self.reopened_by_membership_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "submitted_at": self.submitted_at,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "Proposal":
        # Fase 21: documents written before this phase have a single
        # `snapshot` slot, never a `snapshots` array - derive a one-element
        # history from it so `current_snapshot` keeps working unchanged for
        # every pre-existing Proposal, with no backfill migration needed.
        if "snapshots" in doc:
            snapshots = [ProposalSnapshot.from_document(s) for s in doc["snapshots"]]
        else:
            legacy_snapshot = doc.get("snapshot")
            snapshots = [ProposalSnapshot.from_document(legacy_snapshot)] if legacy_snapshot else []
        return Proposal(
            id=doc["_id"],
            tenant_id=doc["tenant_id"],
            evaluation_id=doc["evaluation_id"],
            vendor_org_id=doc["vendor_org_id"],
            status=doc["status"],
            version=doc["version"],
            round=doc.get("round", 0),
            answers=[ProposalAnswer.from_document(a) for a in doc.get("answers", [])],
            cost_items=[CostItem.from_document(c) for c in doc.get("cost_items", [])],
            snapshots=snapshots,
            reopened_reason=doc.get("reopened_reason"),
            reopened_at=doc.get("reopened_at"),
            reopened_by_membership_id=doc.get("reopened_by_membership_id"),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
            submitted_at=doc.get("submitted_at"),
        )
