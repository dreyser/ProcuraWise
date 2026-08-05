"""Fase 21 (ADR 0013) - model-level coverage for the versioning fields added
on top of the pre-existing Proposal/ProposalAnswer/CostItem/ProposalSnapshot
shapes: `round`, `snapshots` (replacing the old single `snapshot` slot),
`status`/`source_proposal_version`, and safe defaults for every document
written before this phase existed."""

from datetime import UTC, datetime
from decimal import Decimal

from procurawise.evaluations.models import Requirement
from procurawise.proposals.models import Proposal, ProposalAnswer, ProposalSnapshot
from procurawise.tco.models import CostItem


def _requirement() -> Requirement:
    return Requirement.create(
        dimension="functional",
        category="Core",
        title="Req",
        description="d",
        priority="important",
        response_type="text",
        weight=40.0,
        required=False,
        display_order=1,
    )


def _snapshot(round_: int = 0) -> ProposalSnapshot:
    now = datetime.now(UTC)
    return ProposalSnapshot(
        snapshot_id=f"snap-{round_}",
        taken_at=now,
        evaluation_id="eval-1",
        evaluation_name="Eval",
        vendor_org_id="vendor-1",
        vendor_org_name="Vendor",
        requirements=[_requirement()],
        answers=[
            ProposalAnswer(requirement_id="req-1", value="x", vendor_comment=None, updated_at=now)
        ],
        submitted_by_membership_id="m-1",
        submitted_at=now,
        document_ids=[],
        cost_items=[],
        tco_result=None,
        round=round_,
    )


def test_proposal_answer_defaults_to_modified_with_no_source_version() -> None:
    answer = ProposalAnswer(
        requirement_id="req-1", value="x", vendor_comment=None, updated_at=datetime.now(UTC)
    )
    assert answer.status == "modified"
    assert answer.source_proposal_version is None


def test_proposal_answer_round_trips_inherited_status_and_source_version() -> None:
    answer = ProposalAnswer(
        requirement_id="req-1",
        value="x",
        vendor_comment=None,
        updated_at=datetime.now(UTC),
        status="inherited",
        source_proposal_version=0,
    )
    restored = ProposalAnswer.from_document(answer.to_document())
    assert restored == answer


def test_proposal_answer_from_legacy_document_without_version_fields() -> None:
    """A Fase 1-20 ProposalAnswer document never had status/
    source_proposal_version - must deserialize with safe defaults, not
    KeyError."""
    legacy_doc = {
        "requirement_id": "req-1",
        "value": "x",
        "vendor_comment": None,
        "updated_at": datetime.now(UTC),
    }
    restored = ProposalAnswer.from_document(legacy_doc)
    assert restored.status == "modified"
    assert restored.source_proposal_version is None


def _cost_item() -> CostItem:
    return CostItem.create(
        concept="Licencia",
        category="recurring",
        description=None,
        billing_unit="usuario",
        quantity=Decimal(10),
        unit_price=Decimal(100),
        currency="MXN",
        frequency_per_year=Decimal(1),
        tax_pct=Decimal(0),
        discount_pct=Decimal(0),
        year_start=1,
        year_end=1,
        annual_increment_pct=Decimal(0),
        mandatory=False,
        cost_type="recurring",
        notes=None,
    )


def test_cost_item_defaults_to_modified_with_no_source_version() -> None:
    item = _cost_item()
    assert item.status == "modified"
    assert item.source_proposal_version is None


def test_cost_item_round_trips_removed_status_and_source_version() -> None:
    from dataclasses import replace

    item = replace(_cost_item(), status="removed", source_proposal_version=0)
    restored = CostItem.from_document(item.to_document())
    assert restored == item


def test_proposal_snapshot_round_defaults_to_zero_for_legacy_documents() -> None:
    snapshot = _snapshot(round_=0)
    doc = snapshot.to_document()
    del doc["round"]
    restored = ProposalSnapshot.from_document(doc)
    assert restored.round == 0


def test_proposal_current_snapshot_is_the_last_element_of_snapshots() -> None:
    from dataclasses import replace

    round0 = _snapshot(round_=0)
    round1 = _snapshot(round_=1)
    proposal = Proposal.create(tenant_id="t", evaluation_id="e", vendor_org_id="v")
    proposal = replace(proposal, snapshots=[round0, round1], round=1, status="submitted")
    assert proposal.current_snapshot == round1
    assert proposal.snapshots == [round0, round1]


def test_proposal_from_legacy_document_derives_snapshots_from_single_slot() -> None:
    """Every Proposal document written before Fase 21 has a single
    `snapshot` key, never `snapshots`/`round`/`reopened_*` - must
    deserialize into a one-element history with round=0, not KeyError or
    silently drop the submitted snapshot."""
    proposal = Proposal.create(tenant_id="t", evaluation_id="e", vendor_org_id="v")
    snapshot = _snapshot(round_=0)
    legacy_doc = proposal.to_document()
    del legacy_doc["snapshots"]
    del legacy_doc["reopened_reason"]
    del legacy_doc["reopened_at"]
    del legacy_doc["reopened_by_membership_id"]
    del legacy_doc["round"]
    legacy_doc["status"] = "submitted"
    legacy_doc["snapshot"] = snapshot.to_document()

    restored = Proposal.from_document(legacy_doc)
    assert restored.round == 0
    assert restored.reopened_reason is None
    assert restored.current_snapshot is not None
    assert restored.current_snapshot.snapshot_id == snapshot.snapshot_id
    assert restored.snapshots == [restored.current_snapshot]


def test_proposal_from_legacy_document_without_any_snapshot_is_empty_history() -> None:
    proposal = Proposal.create(tenant_id="t", evaluation_id="e", vendor_org_id="v")
    legacy_doc = proposal.to_document()
    del legacy_doc["snapshots"]
    legacy_doc["snapshot"] = None

    restored = Proposal.from_document(legacy_doc)
    assert restored.snapshots == []
    assert restored.current_snapshot is None
