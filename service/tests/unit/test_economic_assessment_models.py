from procurawise.scoring.models import CriterionScore, EconomicAssessment


def _scores() -> list[CriterionScore]:
    return [
        CriterionScore(criterion_key="payment_terms", score=4, comment=None),
        CriterionScore(
            criterion_key="price_protection", score=0, comment="Sin protección de precio"
        ),
        CriterionScore(
            criterion_key="contractual_flexibility", score=None, comment="No aplica a este contrato"
        ),
        CriterionScore(criterion_key="discounts_incentives", score=3, comment=None),
        CriterionScore(
            criterion_key="billing_transparency", score=5, comment="Facturación clara y detallada"
        ),
    ]


def test_economic_assessment_create_defaults_version_to_one() -> None:
    assessment = EconomicAssessment.create(
        tenant_id="t",
        evaluation_id="eval-1",
        proposal_id="proposal-1",
        commercial_scores=_scores(),
        risk_scores=_scores(),
        membership_id="m-1",
    )
    assert assessment.version == 1
    assert assessment.created_at == assessment.updated_at


def test_economic_assessment_round_trips_through_document() -> None:
    assessment = EconomicAssessment.create(
        tenant_id="t",
        evaluation_id="eval-1",
        proposal_id="proposal-1",
        commercial_scores=_scores(),
        risk_scores=_scores(),
        membership_id="m-1",
    )
    restored = EconomicAssessment.from_document(assessment.to_document())
    assert restored == assessment


def test_criterion_score_round_trips_through_document_including_na() -> None:
    na_score = CriterionScore(
        criterion_key="variable_cost_exposure", score=None, comment="N/A - contrato fijo"
    )
    restored = CriterionScore.from_document(na_score.to_document())
    assert restored == na_score
    assert restored.score is None
