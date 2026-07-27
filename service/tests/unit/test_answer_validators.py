import pytest

from procurawise.evaluations.models import Requirement, ResponseType
from procurawise.proposals.exceptions import AnswerValidationError
from procurawise.proposals.service import validate_answer_value


def _requirement(response_type: ResponseType, options: list[str] | None = None) -> Requirement:
    return Requirement.create(
        dimension="functional",
        category="c",
        title="t",
        description="d",
        priority="important",
        response_type=response_type,
        weight=10.0,
        required=True,
        display_order=1,
        options=options,
    )


def test_none_value_is_always_accepted() -> None:
    validate_answer_value(_requirement("text"), None)


@pytest.mark.parametrize(
    "value",
    ["compliant", "partially_compliant", "non_compliant"],
)
def test_compliant_status_accepts_known_values(value: str) -> None:
    validate_answer_value(_requirement("compliant_status"), value)


def test_compliant_status_rejects_unknown_value() -> None:
    with pytest.raises(AnswerValidationError):
        validate_answer_value(_requirement("compliant_status"), "maybe")


def test_text_requires_string() -> None:
    validate_answer_value(_requirement("text"), "hello")
    with pytest.raises(AnswerValidationError):
        validate_answer_value(_requirement("text"), 123)


def test_single_choice_requires_value_in_options() -> None:
    requirement = _requirement("single_choice", options=["a", "b"])
    validate_answer_value(requirement, "a")
    with pytest.raises(AnswerValidationError):
        validate_answer_value(requirement, "c")


def test_multi_choice_requires_subset_of_options() -> None:
    requirement = _requirement("multi_choice", options=["a", "b", "c"])
    validate_answer_value(requirement, ["a", "c"])
    with pytest.raises(AnswerValidationError):
        validate_answer_value(requirement, ["a", "z"])
    with pytest.raises(AnswerValidationError):
        validate_answer_value(requirement, "a")


def test_number_rejects_bool_and_non_numeric() -> None:
    validate_answer_value(_requirement("number"), 42)
    validate_answer_value(_requirement("number"), 4.2)
    with pytest.raises(AnswerValidationError):
        validate_answer_value(_requirement("number"), True)
    with pytest.raises(AnswerValidationError):
        validate_answer_value(_requirement("number"), "42")


def test_percentage_must_be_between_0_and_100() -> None:
    validate_answer_value(_requirement("percentage"), 0)
    validate_answer_value(_requirement("percentage"), 100)
    with pytest.raises(AnswerValidationError):
        validate_answer_value(_requirement("percentage"), 101)
    with pytest.raises(AnswerValidationError):
        validate_answer_value(_requirement("percentage"), -1)


def test_date_requires_iso_format() -> None:
    validate_answer_value(_requirement("date"), "2026-07-27")
    with pytest.raises(AnswerValidationError):
        validate_answer_value(_requirement("date"), "27/07/2026")


def test_url_requires_http_scheme() -> None:
    validate_answer_value(_requirement("url"), "https://example.com")
    with pytest.raises(AnswerValidationError):
        validate_answer_value(_requirement("url"), "ftp://example.com")


def test_comment_accepts_free_text() -> None:
    validate_answer_value(_requirement("comment"), "cualquier texto")


def test_currency_requires_amount_and_valid_currency_code() -> None:
    requirement = _requirement("currency")
    validate_answer_value(requirement, {"amount": 100.0, "currency_code": "MXN"})
    validate_answer_value(requirement, {"amount": 0, "currency_code": "USD"})
    with pytest.raises(AnswerValidationError):
        validate_answer_value(requirement, {"amount": -1, "currency_code": "USD"})
    with pytest.raises(AnswerValidationError):
        validate_answer_value(requirement, {"amount": 1, "currency_code": "EUR"})
    with pytest.raises(AnswerValidationError):
        validate_answer_value(requirement, "not a dict")
