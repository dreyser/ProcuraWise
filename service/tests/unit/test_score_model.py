import pytest

from procurawise.scoring.models import Score


def _score(score_value: int, priority: str = "mandatory", weight: float = 40.0) -> Score:
    return Score.create(
        tenant_id="t",
        evaluation_id="e",
        proposal_id="p",
        snapshot_id="s",
        requirement_id="r",
        dimension="functional",
        priority=priority,
        requirement_weight=weight,
        score=score_value,
        comment=None,
        membership_id="m",
    )


@pytest.mark.parametrize(
    ("score_value", "weight", "expected"),
    [
        (5, 40.0, 40.0),
        (0, 40.0, 0.0),
        (3, 40.0, 24.0),
        (4, 20.0, 16.0),
        (1, 10.0, 2.0),
    ],
)
def test_weighted_points_formula_and_rounding(
    score_value: int, weight: float, expected: float
) -> None:
    score = _score(score_value, weight=weight)
    assert score.weighted_points == expected


@pytest.mark.parametrize(
    ("score_value", "priority", "expected_alert"),
    [
        (0, "mandatory", True),
        (1, "mandatory", True),
        (4, "mandatory", True),
        (5, "mandatory", False),
        (0, "important", False),
        (0, "desirable", False),
    ],
)
def test_mandatory_alert_threshold(score_value: int, priority: str, expected_alert: bool) -> None:
    score = _score(score_value, priority=priority)
    assert score.mandatory_alert is expected_alert
