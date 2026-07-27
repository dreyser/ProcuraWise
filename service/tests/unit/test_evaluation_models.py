import pytest

from procurawise.evaluations.models import Evaluation, Requirement


def test_evaluation_create_defaults_to_draft_with_no_vendors() -> None:
    evaluation = Evaluation.create(
        tenant_id="t", name="RFP", description="", created_by_membership_id="m"
    )
    assert evaluation.status == "draft"
    assert evaluation.requirements == []
    assert evaluation.linked_vendor_count == 0
    assert evaluation.collecting_responses_started_at is None


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
