from dataclasses import replace
from datetime import UTC, datetime

from procurawise.qna.models import AnswerVersion, Question


def _question(**overrides: object) -> Question:
    defaults: dict[str, object] = dict(
        tenant_id="t1",
        evaluation_id="e1",
        proposal_id="p1",
        vendor_org_id="v1",
        requirement_id="r1",
        scope="requirement",
        body="Does this support SSO?",
        created_by_membership_id="m1",
    )
    defaults.update(overrides)
    return Question.create(**defaults)  # type: ignore[arg-type]


def test_create_defaults_to_open_with_no_answer() -> None:
    question = _question()
    assert question.status == "open"
    assert question.version == 1
    assert question.current_answer is None
    assert question.answer_history == []


def test_create_supports_general_scope_without_requirement() -> None:
    question = _question(scope="general", requirement_id=None)
    assert question.requirement_id is None
    assert question.scope == "general"


def test_question_round_trips_through_document() -> None:
    question = _question()
    restored = Question.from_document(question.to_document())
    assert restored == question


def test_question_with_answer_history_round_trips() -> None:
    question = _question()
    first_answer = AnswerVersion(
        version=1,
        body="Yes, via SAML.",
        visibility="private",
        answered_by_membership_id="owner1",
        answered_at=datetime.now(UTC),
    )
    second_answer = AnswerVersion(
        version=2,
        body="Yes, via SAML and OIDC.",
        visibility="published_anonymized",
        answered_by_membership_id="owner1",
        answered_at=datetime.now(UTC),
    )
    answered = replace(
        question,
        status="answered",
        version=3,
        current_answer=second_answer,
        answer_history=[first_answer],
    )

    restored = Question.from_document(answered.to_document())
    assert restored == answered
    assert restored.current_answer is not None
    assert restored.current_answer.visibility == "published_anonymized"
    assert restored.answer_history == [first_answer]


def test_answer_version_round_trips_through_document() -> None:
    answer = AnswerVersion(
        version=1,
        body="Private answer",
        visibility="private",
        answered_by_membership_id="owner1",
        answered_at=datetime.now(UTC),
    )
    restored = AnswerVersion.from_document(answer.to_document())
    assert restored == answer
