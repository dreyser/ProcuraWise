"""Fase 23 - pure functions: already-fetched domain data in, a
ReportDocument/ReportWorkbook out. No Mongo/Blob access here (same "pure
function, no infrastructure" principle as tco.service.TcoService.calculate()/
scoring.economic_formulas) - service.py fetches everything these functions
need and owns all I/O."""

from datetime import UTC, datetime
from typing import Any

from procurawise.decisions.models import DecisionSnapshot
from procurawise.evaluations.models import Evaluation, EvaluationSnapshot, Requirement
from procurawise.qna.models import Question
from procurawise.reports.render_types import (
    ReportDocument,
    ReportSection,
    ReportSheet,
    ReportTable,
    ReportWorkbook,
)
from procurawise.tco.models import TcoResult

_DIMENSION_LABELS = {"functional": "Funcional", "technical": "Técnico", "economic": "Económico"}
_PRIORITY_LABELS = {"mandatory": "Obligatorio", "important": "Importante", "desirable": "Deseable"}
_OUTCOME_LABELS = {"selected": "Proveedor seleccionado", "void": "Proceso declarado desierto"}


def _now_line() -> str:
    return f"Fecha de generación: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}"


def _requirement_row(requirement: Requirement) -> list[str]:
    return [
        _DIMENSION_LABELS.get(requirement.dimension, requirement.dimension),
        requirement.category,
        requirement.title,
        _PRIORITY_LABELS.get(requirement.priority, requirement.priority),
        f"{requirement.weight:g}",
        "Sí" if requirement.required else "No",
    ]


def assemble_rfp_document(
    evaluation: Evaluation, snapshot: EvaluationSnapshot | None
) -> ReportDocument:
    requirements = snapshot.requirements if snapshot is not None else evaluation.requirements
    version_line = (
        f"Versión publicada (snapshot {snapshot.snapshot_id})"
        if snapshot is not None
        else "Borrador (aún no publicada)"
    )
    return ReportDocument(
        title="Documento formal de RFP",
        subtitle=evaluation.name,
        metadata_lines=[version_line, _now_line()],
        sections=[
            ReportSection(heading="Descripción", paragraphs=[evaluation.description or "—"]),
            ReportSection(
                heading="Requerimientos",
                table=ReportTable(
                    headers=[
                        "Dimensión",
                        "Categoría",
                        "Título",
                        "Prioridad",
                        "Peso",
                        "Obligatorio",
                    ],
                    rows=[_requirement_row(r) for r in requirements],
                ),
            ),
        ],
    )


def assemble_requirements_matrix(
    evaluation: Evaluation, snapshot: EvaluationSnapshot | None
) -> ReportWorkbook:
    requirements = snapshot.requirements if snapshot is not None else evaluation.requirements
    return ReportWorkbook(
        title=f"Matriz de requerimientos — {evaluation.name}",
        metadata_lines=[_now_line()],
        sheets=[
            ReportSheet(
                name="Requerimientos",
                headers=[
                    "Dimensión",
                    "Categoría",
                    "Título",
                    "Descripción",
                    "Prioridad",
                    "Peso",
                    "Tipo de respuesta",
                    "Obligatorio",
                ],
                rows=[
                    [
                        _DIMENSION_LABELS.get(r.dimension, r.dimension),
                        r.category,
                        r.title,
                        r.description,
                        _PRIORITY_LABELS.get(r.priority, r.priority),
                        float(r.weight),
                        r.response_type,
                        "Sí" if r.required else "No",
                    ]
                    for r in requirements
                ],
            )
        ],
    )


def _final_result_cell(proposal: dict[str, Any]) -> str:
    final = proposal.get("final_result")
    if final is None:
        return "No disponible"
    return f"{final['total_points']} / {final['maximum_points']}"


def _subtotal_cell(subtotal: dict[str, Any]) -> str:
    return f"{subtotal['earned_points']} / {subtotal['maximum_points']}"


def _economic_cell(economic: dict[str, Any]) -> str:
    if economic["status"] != "available":
        return "No disponible"
    return _subtotal_cell(economic)


def assemble_vendor_comparison(evaluation: Evaluation, results: dict[str, Any]) -> ReportDocument:
    rows = [
        [
            proposal["vendor_org_name"],
            _subtotal_cell(proposal["functional"]),
            _subtotal_cell(proposal["technical"]),
            _economic_cell(proposal["economic"]),
            _final_result_cell(proposal),
            str(proposal["mandatory_alerts_count"]),
        ]
        for proposal in results["proposals"]
    ]
    return ReportDocument(
        title="Comparativo ejecutivo de proveedores",
        subtitle=evaluation.name,
        metadata_lines=[results["disclaimer"], _now_line()],
        sections=[
            ReportSection(
                heading="Resultados por proveedor",
                paragraphs=[
                    "Orden estable por proveedor - no es un ranking ni implica adjudicación."
                ],
                table=ReportTable(
                    headers=[
                        "Proveedor",
                        "Funcional",
                        "Técnico",
                        "Económico",
                        "Resultado final",
                        "Alertas obligatorias",
                    ],
                    rows=rows,
                ),
            )
        ],
    )


def assemble_scoring_detail(evaluation: Evaluation, results: dict[str, Any]) -> ReportDocument:
    sections = []
    for proposal in results["proposals"]:
        rows = [
            [
                _DIMENSION_LABELS.get(score["dimension"], score["dimension"]),
                score["title"],
                _PRIORITY_LABELS.get(score["priority"], score["priority"]),
                str(score["raw_score"]),
                str(score["weighted_points"]),
                score["comment"] or "—",
            ]
            for score in proposal["scores"]
        ]
        sections.append(
            ReportSection(
                heading=proposal["vendor_org_name"],
                table=ReportTable(
                    headers=[
                        "Dimensión",
                        "Requerimiento",
                        "Prioridad",
                        "Calificación",
                        "Puntos ponderados",
                        "Comentario",
                    ],
                    rows=rows,
                ),
            )
        )
    return ReportDocument(
        title="Reporte detallado de scoring",
        subtitle=evaluation.name,
        metadata_lines=[results["disclaimer"], _now_line()],
        sections=sections,
    )


def assemble_risk_analysis(evaluation: Evaluation, results: dict[str, Any]) -> ReportDocument:
    sections = []
    for proposal in results["proposals"]:
        flagged = [score for score in proposal["scores"] if score["mandatory_alert"]]
        rows = [
            [score["title"], str(score["raw_score"]), score["comment"] or "—"] for score in flagged
        ]
        sections.append(
            ReportSection(
                heading=f"{proposal['vendor_org_name']} — {len(flagged)} alerta(s) obligatoria(s)",
                table=ReportTable(
                    headers=["Requerimiento", "Calificación", "Comentario"], rows=rows
                )
                if rows
                else None,
                paragraphs=[] if rows else ["Sin alertas obligatorias."],
            )
        )
    return ReportDocument(
        title="Análisis de riesgos y excepciones",
        subtitle=evaluation.name,
        metadata_lines=[
            "Un requerimiento obligatorio calificado por debajo de 5 genera una alerta "
            "informativa - nunca descalifica automáticamente a un proveedor.",
            _now_line(),
        ],
        sections=sections,
    )


def assemble_tco_breakdown(
    evaluation: Evaluation, proposal_tco: list[tuple[str, TcoResult]]
) -> ReportWorkbook:
    by_year_rows: list[list[Any]] = []
    by_category_rows: list[list[Any]] = []
    summary_rows: list[list[Any]] = []
    for vendor_org_name, tco in proposal_tco:
        for year, amount in sorted(tco.by_year.items()):
            by_year_rows.append([vendor_org_name, year, float(amount), tco.base_currency])
        for category, amount in sorted(tco.by_category.items()):
            by_category_rows.append([vendor_org_name, category, float(amount), tco.base_currency])
        summary_rows.append(
            [
                vendor_org_name,
                float(tco.grand_total),
                float(tco.grand_total_with_tax),
                tco.base_currency,
            ]
        )
    return ReportWorkbook(
        title=f"Tabla de TCO — {evaluation.name}",
        metadata_lines=[
            f"Horizonte: {evaluation.tco_horizon_years} año(s)",
            f"Moneda base: {evaluation.base_currency}",
            _now_line(),
        ],
        sheets=[
            ReportSheet(
                name="Resumen",
                headers=["Proveedor", "TCO total", "TCO total con impuestos", "Moneda"],
                rows=summary_rows,
            ),
            ReportSheet(
                name="Por año", headers=["Proveedor", "Año", "Monto", "Moneda"], rows=by_year_rows
            ),
            ReportSheet(
                name="Por categoría",
                headers=["Proveedor", "Categoría", "Monto", "Moneda"],
                rows=by_category_rows,
            ),
        ],
    )


def assemble_decision_record(evaluation: Evaluation, snapshot: DecisionSnapshot) -> ReportDocument:
    outcome_line = _OUTCOME_LABELS.get(snapshot.outcome, snapshot.outcome)
    if snapshot.selected_vendor_org_name:
        outcome_line = f"{outcome_line} — {snapshot.selected_vendor_org_name}"
    paragraphs = [f"Resultado: {outcome_line}"]
    if snapshot.void_reason:
        paragraphs.append(f"Motivo: {snapshot.void_reason}")
    paragraphs.append(f"Justificación: {snapshot.justification}")
    paragraphs.append(f"Decidida el {snapshot.decided_at.isoformat()}.")

    comparison_rows = [
        [proposal["vendor_org_name"], _final_result_cell(proposal)]
        for proposal in snapshot.proposal_results
    ]
    return ReportDocument(
        title="Acta de decisión",
        subtitle=evaluation.name,
        metadata_lines=[f"Memo de cierre congelado (snapshot {snapshot.snapshot_id})", _now_line()],
        sections=[
            ReportSection(heading="Decisión aprobada", paragraphs=paragraphs),
            ReportSection(
                heading="Contexto de resultados al momento de aprobar",
                table=ReportTable(headers=["Proveedor", "Resultado final"], rows=comparison_rows),
            ),
        ],
    )


def assemble_qna_summary(evaluation: Evaluation, questions: list[Question]) -> ReportDocument:
    rows = []
    for question in questions:
        answer_body = question.current_answer.body if question.current_answer else "Sin responder"
        rows.append([question.scope, question.body, answer_body, question.status])
    return ReportDocument(
        title="Resumen de preguntas y respuestas",
        subtitle=evaluation.name,
        metadata_lines=[_now_line()],
        sections=[
            ReportSection(
                heading="Preguntas y respuestas",
                table=ReportTable(
                    headers=["Alcance", "Pregunta", "Respuesta", "Estado"], rows=rows
                ),
            )
        ],
    )
