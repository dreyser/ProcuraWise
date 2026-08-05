from decimal import Decimal

from procurawise.evaluations.models import DEFAULT_COMMERCIAL_WEIGHTS, DEFAULT_RISK_WEIGHTS
from procurawise.scoring.economic_formulas import (
    calculate_economic_points,
    calculate_rubric_pct,
    calculate_tco_normalized_pct,
)
from procurawise.scoring.models import CriterionScore

# --- calculate_tco_normalized_pct ---


def test_tco_normalization_two_proposals_lowest_gets_100() -> None:
    result = calculate_tco_normalized_pct({"p1": Decimal("1000"), "p2": Decimal("2000")})
    assert result["p1"].status == "available"
    assert result["p1"].pct == 100.0
    assert result["p2"].status == "available"
    assert result["p2"].pct == 50.0


def test_tco_normalization_single_proposal_gets_100() -> None:
    result = calculate_tco_normalized_pct({"p1": Decimal("5000")})
    assert result["p1"].status == "available"
    assert result["p1"].pct == 100.0


def test_tco_normalization_tie_both_get_100() -> None:
    result = calculate_tco_normalized_pct({"p1": Decimal("1000"), "p2": Decimal("1000")})
    assert result["p1"].pct == 100.0
    assert result["p2"].pct == 100.0


def test_tco_normalization_zero_total_is_no_comparable_and_excluded_from_denominator() -> None:
    result = calculate_tco_normalized_pct(
        {"p1": Decimal("0"), "p2": Decimal("1000"), "p3": Decimal("2000")}
    )
    assert result["p1"].status == "no_comparable"
    assert result["p1"].pct is None
    # p2 (the real lowest, ignoring p1's zero) still gets 100 - p1's zero
    # never becomes the "menor válido".
    assert result["p2"].pct == 100.0
    assert result["p3"].pct == 50.0


def test_tco_normalization_missing_tco_result_is_no_comparable() -> None:
    result = calculate_tco_normalized_pct({"p1": None, "p2": Decimal("1000")})
    assert result["p1"].status == "no_comparable"
    assert result["p1"].pct is None
    assert result["p2"].status == "available"
    assert result["p2"].pct == 100.0


def test_tco_normalization_all_missing_or_zero_none_comparable() -> None:
    result = calculate_tco_normalized_pct({"p1": None, "p2": Decimal("0")})
    assert result["p1"].status == "no_comparable"
    assert result["p2"].status == "no_comparable"


def test_tco_normalization_negative_total_is_no_comparable() -> None:
    result = calculate_tco_normalized_pct({"p1": Decimal("-5"), "p2": Decimal("100")})
    assert result["p1"].status == "no_comparable"
    assert result["p2"].pct == 100.0


# --- calculate_rubric_pct ---


def _full_scores(score_value: int) -> list[CriterionScore]:
    return [
        CriterionScore(criterion_key=key, score=score_value, comment=None)
        for key in DEFAULT_COMMERCIAL_WEIGHTS
    ]


def test_rubric_pct_all_max_scores_is_100() -> None:
    pct = calculate_rubric_pct(_full_scores(5), DEFAULT_COMMERCIAL_WEIGHTS)
    assert pct == 100.0


def test_rubric_pct_all_zero_scores_is_0() -> None:
    pct = calculate_rubric_pct(_full_scores(0), DEFAULT_COMMERCIAL_WEIGHTS)
    assert pct == 0.0


def test_rubric_pct_no_scores_yet_is_none() -> None:
    scores = [
        CriterionScore(criterion_key=key, score=None, comment=None)
        for key in DEFAULT_COMMERCIAL_WEIGHTS
    ]
    assert calculate_rubric_pct(scores, DEFAULT_COMMERCIAL_WEIGHTS) is None


def test_rubric_pct_excludes_na_from_denominator() -> None:
    # payment_terms (25%) is N/A; the other 4 groups (75% total) all score 5.
    scores = [
        CriterionScore(criterion_key="payment_terms", score=None, comment="No aplica"),
        CriterionScore(criterion_key="price_protection", score=5, comment=None),
        CriterionScore(criterion_key="contractual_flexibility", score=5, comment=None),
        CriterionScore(criterion_key="discounts_incentives", score=5, comment=None),
        CriterionScore(criterion_key="billing_transparency", score=5, comment=None),
    ]
    pct = calculate_rubric_pct(scores, DEFAULT_COMMERCIAL_WEIGHTS)
    # Renormalized over the 75% of applicable weight - full marks on all
    # applicable criteria should still yield 100, not 75.
    assert pct == 100.0


def test_rubric_pct_partial_scores_weighted_correctly() -> None:
    scores = [
        CriterionScore(criterion_key="variable_cost_exposure", score=5, comment=None),  # 30%
        CriterionScore(
            criterion_key="increases_indexation", score=0, comment="Sin protección"
        ),  # 25%
    ]
    pct = calculate_rubric_pct(scores, DEFAULT_RISK_WEIGHTS)
    # (5/5)*30 + (0/5)*25 = 30, over total applicable weight 55 -> 30/55*100
    assert pct == round(30 / 55 * 100, 2)


# --- calculate_economic_points ---


def test_economic_points_all_components_available() -> None:
    result = calculate_economic_points(tco_pct=100.0, commercial_pct=100.0, risk_pct=100.0)
    assert result.status == "available"
    assert result.earned_points == 40.0  # ECONOMIC_MAX_POINTS at full marks


def test_economic_points_matches_70_15_15_weighting() -> None:
    result = calculate_economic_points(tco_pct=100.0, commercial_pct=0.0, risk_pct=0.0)
    assert result.status == "available"
    assert result.earned_points == 28.0  # 40 * 0.70


def test_economic_points_missing_tco_is_not_available() -> None:
    result = calculate_economic_points(tco_pct=None, commercial_pct=100.0, risk_pct=100.0)
    assert result.status == "not_available"
    assert result.earned_points is None


def test_economic_points_missing_commercial_is_not_available() -> None:
    result = calculate_economic_points(tco_pct=100.0, commercial_pct=None, risk_pct=100.0)
    assert result.status == "not_available"


def test_economic_points_missing_risk_is_not_available() -> None:
    result = calculate_economic_points(tco_pct=100.0, commercial_pct=100.0, risk_pct=None)
    assert result.status == "not_available"


def test_economic_points_zero_across_the_board() -> None:
    result = calculate_economic_points(tco_pct=0.0, commercial_pct=0.0, risk_pct=0.0)
    assert result.status == "available"
    assert result.earned_points == 0.0
