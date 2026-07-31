from datetime import UTC, datetime

import pytest

from procurawise.evaluations.models import Evaluation, EvaluationSnapshot, Requirement


def test_evaluation_create_defaults_to_draft_with_no_vendors() -> None:
    evaluation = Evaluation.create(
        tenant_id="t", name="RFP", description="", created_by_membership_id="m"
    )
    assert evaluation.status == "draft"
    assert evaluation.requirements == []
    assert evaluation.linked_vendor_count == 0
    assert evaluation.collecting_responses_started_at is None


def test_evaluation_create_defaults_approval_fields_to_not_requested() -> None:
    evaluation = Evaluation.create(
        tenant_id="t", name="RFP", description="", created_by_membership_id="m"
    )
    assert evaluation.approval_status == "not_requested"
    assert evaluation.approver_membership_id is None
    assert evaluation.response_deadline is None
    assert evaluation.approval_snapshot_id is None


def test_evaluation_from_document_defaults_approval_status_for_pre_phase12_documents() -> None:
    """Evaluations persisted before Fase 12 have none of the new approval_*
    keys (plan §29: no backfill) - from_document must still load them."""
    evaluation = Evaluation.create(
        tenant_id="t", name="RFP", description="", created_by_membership_id="m"
    )
    doc = evaluation.to_document()
    for key in [
        "approval_status",
        "approver_membership_id",
        "response_deadline",
        "approval_requested_at",
        "approval_requested_by_membership_id",
        "approval_decided_at",
        "approval_decided_by_membership_id",
        "approval_comment",
        "approval_snapshot_id",
    ]:
        del doc[key]
    restored = Evaluation.from_document(doc)
    assert restored.approval_status == "not_requested"
    assert restored.approver_membership_id is None
    assert restored.approval_snapshot_id is None


def test_requirement_create_rejects_single_choice_without_options() -> None:
    with pytest.raises(ValueError, match="options"):
        Requirement.create(
            dimension="functional",
            category="c",
            title="t",
            description="d",
            priority="important",
            response_type="single_choice",
            weight=10.0,
            required=True,
            display_order=1,
        )


def test_requirement_create_accepts_single_choice_with_options() -> None:
    requirement = Requirement.create(
        dimension="functional",
        category="c",
        title="t",
        description="d",
        priority="important",
        response_type="single_choice",
        weight=10.0,
        required=True,
        display_order=1,
        options=["a", "b"],
    )
    assert requirement.options == ["a", "b"]


def test_requirement_round_trips_through_document() -> None:
    requirement = Requirement.create(
        dimension="technical",
        category="c",
        title="t",
        description="d",
        priority="mandatory",
        response_type="number",
        weight=5.0,
        required=False,
        display_order=2,
    )
    restored = Requirement.from_document(requirement.to_document())
    assert restored == requirement


def test_evaluation_round_trips_through_document_with_requirements() -> None:
    requirement = Requirement.create(
        dimension="functional",
        category="c",
        title="t",
        description="d",
        priority="desirable",
        response_type="text",
        weight=1.0,
        required=False,
        display_order=1,
    )
    evaluation = Evaluation.create(
        tenant_id="t", name="RFP", description="d", created_by_membership_id="m"
    )
    from dataclasses import replace

    evaluation = replace(evaluation, requirements=[requirement])
    restored = Evaluation.from_document(evaluation.to_document())
    assert restored == evaluation


def test_evaluation_snapshot_round_trips_through_document() -> None:
    requirement = Requirement.create(
        dimension="functional",
        category="c",
        title="t",
        description="d",
        priority="mandatory",
        response_type="text",
        weight=40.0,
        required=True,
        display_order=1,
    )
    now = datetime.now(UTC)
    snapshot = EvaluationSnapshot(
        snapshot_id="eval-1",
        tenant_id="t",
        evaluation_id="eval-1",
        taken_at=now,
        evaluation_name="RFP",
        evaluation_description="d",
        requirements=[requirement],
        dimension_weights={"functional": 40.0, "technical": 20.0},
        linked_vendor_org_ids=["v1"],
        vendor_org_names={"v1": "Vendor One"},
        response_deadline=now,
        approver_membership_id="approver-1",
        approval_requested_at=now,
        approval_requested_by_membership_id="owner-1",
        approval_decided_at=now,
        approval_decided_by_membership_id="approver-1",
        approval_comment="Looks good",
        published_by_membership_id="owner-1",
        published_at=now,
    )
    restored = EvaluationSnapshot.from_document(snapshot.to_document())
    assert restored == snapshot
