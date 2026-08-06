from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

from procurawise.decisions.models import DecisionSnapshot
from procurawise.evaluations.models import Evaluation, Requirement
from procurawise.qna.models import AnswerVersion, Question
from procurawise.reports import assembly
from procurawise.tco.models import TcoResult


def _evaluation() -> Evaluation:
    evaluation = Evaluation.create(
        tenant_id="tenant-1",
        name="RFP de prueba",
        description="desc",
        created_by_membership_id="m-1",
    )
    requirement = Requirement.create(
        dimension="functional",
        category="Core",
        title="Req 1",
        description="d",
        priority="mandatory",
        response_type="text",
        weight=40.0,
        required=True,
        display_order=1,
    )
    return replace(evaluation, requirements=[requirement])


def _results() -> dict:
    return {
        "result_status": "final",
        "is_final": True,
        "scoring_status": "complete",
        "disclaimer": "No constituye recomendacion de adjudicacion.",
        "proposals": [
            {
                "proposal_id": "proposal-1",
                "vendor_org_id": "vendor-1",
                "vendor_org_name": "Proveedor Uno",
                "status": "submitted",
                "functional": {"earned_points": 40.0, "maximum_points": 40.0},
                "technical": {"earned_points": 20.0, "maximum_points": 20.0},
                "economic": {"status": "available", "earned_points": 40.0, "maximum_points": 40.0},
                "partial_result": {
                    "earned_points": 60.0,
                    "maximum_points": 60.0,
                    "model_coverage_percent": 60.0,
                },
                "final_result": {"total_points": 100.0, "maximum_points": 100.0},
                "scores": [
                    {
                        "requirement_id": "req-1",
                        "dimension": "functional",
                        "title": "Req 1",
                        "priority": "mandatory",
                        "raw_score": 1,
                        "comment": "insuficiente",
                        "requirement_weight": 40.0,
                        "weighted_points": 8.0,
                        "version": 1,
                        "evaluator_membership_id": "m-1",
                        "mandatory_alert": True,
                    }
                ],
                "mandatory_alerts_count": 1,
            }
        ],
        "draft_proposals": [],
    }


def test_assemble_vendor_comparison_includes_every_proposal_row() -> None:
    document = assembly.assemble_vendor_comparison(_evaluation(), _results())
    table = document.sections[0].table
    assert table is not None
    assert table.rows == [
        ["Proveedor Uno", "40.0 / 40.0", "20.0 / 20.0", "40.0 / 40.0", "100.0 / 100.0", "1"]
    ]


def test_assemble_risk_analysis_lists_only_flagged_scores() -> None:
    document = assembly.assemble_risk_analysis(_evaluation(), _results())
    section = document.sections[0]
    assert "1 alerta" in section.heading
    assert section.table is not None
    assert section.table.rows == [["Req 1", "1", "insuficiente"]]


def test_assemble_decision_record_reports_selected_vendor() -> None:
    now = datetime.now(UTC)
    snapshot = DecisionSnapshot(
        snapshot_id="eval-1",
        tenant_id="tenant-1",
        evaluation_id="eval-1",
        outcome="selected",
        selected_vendor_org_id="vendor-1",
        selected_vendor_org_name="Proveedor Uno",
        selected_proposal_id="proposal-1",
        selected_proposal_snapshot_id="snap-0",
        void_reason=None,
        justification="Cumple todos los requisitos.",
        approver_membership_id="m-approver",
        decided_at=now,
        decided_by_membership_id="m-approver",
        proposal_results=[
            {
                "vendor_org_name": "Proveedor Uno",
                "final_result": {"total_points": 100.0, "maximum_points": 100.0},
            }
        ],
        taken_at=now,
    )
    document = assembly.assemble_decision_record(_evaluation(), snapshot)
    assert "Proveedor seleccionado — Proveedor Uno" in document.sections[0].paragraphs[0]
    assert "Cumple todos los requisitos." in document.sections[0].paragraphs[1]


def test_assemble_qna_summary_shows_unanswered_as_such() -> None:
    question = Question.create(
        tenant_id="tenant-1",
        evaluation_id="eval-1",
        proposal_id="proposal-1",
        vendor_org_id="vendor-1",
        requirement_id=None,
        scope="general",
        body="¿Cual es el plazo?",
        created_by_membership_id="m-vendor",
    )
    document = assembly.assemble_qna_summary(_evaluation(), [question])
    table = document.sections[0].table
    assert table is not None
    assert table.rows[0][2] == "Sin responder"


def test_assemble_qna_summary_shows_current_answer_body() -> None:
    question = Question.create(
        tenant_id="tenant-1",
        evaluation_id="eval-1",
        proposal_id="proposal-1",
        vendor_org_id="vendor-1",
        requirement_id=None,
        scope="general",
        body="¿Cual es el plazo?",
        created_by_membership_id="m-vendor",
    )
    answered = replace(
        question,
        current_answer=AnswerVersion(
            version=1,
            body="30 dias",
            visibility="published_anonymized",
            answered_by_membership_id="m-owner",
            answered_at=datetime.now(UTC),
        ),
    )
    document = assembly.assemble_qna_summary(_evaluation(), [answered])
    table = document.sections[0].table
    assert table is not None
    assert table.rows[0][2] == "30 dias"


def test_assemble_tco_breakdown_flattens_year_and_category_totals() -> None:
    now = datetime.now(UTC)
    tco = TcoResult(
        base_currency="MXN",
        horizon_years=1,
        by_year={1: Decimal("1000.00")},
        by_year_with_tax={1: Decimal("1160.00")},
        by_category={"recurring": Decimal("1000.00")},
        grand_total=Decimal("1000.00"),
        grand_total_with_tax=Decimal("1160.00"),
        fx_rates_used=[],
        calculated_at=now,
    )
    workbook = assembly.assemble_tco_breakdown(_evaluation(), [("Proveedor Uno", tco)])
    by_year_sheet = next(s for s in workbook.sheets if s.name == "Por año")
    assert by_year_sheet.rows == [["Proveedor Uno", 1, 1000.0, "MXN"]]
