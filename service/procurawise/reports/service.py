import hashlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from procurawise.audit.service import AuditEventService
from procurawise.decisions.service import DecisionService
from procurawise.evaluations.exceptions import EvaluationNotFoundError
from procurawise.evaluations.models import Evaluation, EvaluationSnapshot
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.evaluations.snapshot_repository import EvaluationSnapshotRepository
from procurawise.identity.repository import VendorOrganizationRepository
from procurawise.identity.service import ActorNotFoundError, IdentityService
from procurawise.proposals.models import Proposal
from procurawise.proposals.repository import ProposalRepository
from procurawise.qna.models import Question
from procurawise.qna.repository import QuestionRepository
from procurawise.reports import assembly
from procurawise.reports.exceptions import (
    InvalidReportFormatError,
    ReportNotFoundError,
    ReportNotReadyError,
    ReportNotSucceededError,
)
from procurawise.reports.models import (
    CONTENT_TYPE_BY_FORMAT,
    VALID_FORMATS_BY_TYPE,
    Report,
    ReportFormat,
    ReportType,
)
from procurawise.reports.renderers import csv as csv_renderer
from procurawise.reports.renderers import docx as docx_renderer
from procurawise.reports.renderers import pdf as pdf_renderer
from procurawise.reports.renderers import xlsx as xlsx_renderer
from procurawise.reports.repository import ReportRepository
from procurawise.scoring.service import ScoringService
from procurawise.shared.context import ActorContext
from procurawise.shared.messaging import MessageBus
from procurawise.shared.storage import BlobStorage

logger = logging.getLogger("procurawise.reports")

JOB_TOPIC = "report-generation"

_READINESS_GATED_BY_RESULTS: tuple[ReportType, ...] = (
    "vendor_comparison",
    "scoring_detail",
    "risk_analysis",
    "tco_breakdown",
)


class ReportService:
    """Fase 23 (ADR 0023). request_generation/get_report/list_reports/
    get_download_url are called by the API router; process_generation_job is
    called by the worker's dispatch loop (never by the API directly, per ADR
    0001/0005 - same "worker calls the same code a synchronous call would
    use" principle already applied to ai.service/AIService)."""

    def __init__(
        self,
        reports: ReportRepository,
        evaluations: EvaluationRepository,
        evaluation_snapshots: EvaluationSnapshotRepository,
        proposals: ProposalRepository,
        vendor_orgs: VendorOrganizationRepository,
        scoring: ScoringService,
        decisions: DecisionService,
        qna: QuestionRepository,
        storage: BlobStorage,
        message_bus: MessageBus,
        audit: AuditEventService,
        identity: IdentityService,
        *,
        retention_days: int,
        download_url_ttl_minutes: int,
    ) -> None:
        self._reports = reports
        self._evaluations = evaluations
        self._evaluation_snapshots = evaluation_snapshots
        self._proposals = proposals
        self._vendor_orgs = vendor_orgs
        self._scoring = scoring
        self._decisions = decisions
        self._qna = qna
        self._storage = storage
        self._message_bus = message_bus
        self._audit = audit
        self._identity = identity
        self._retention_days = retention_days
        self._download_url_ttl_minutes = download_url_ttl_minutes

    def _get_evaluation(self, tenant_id: str, evaluation_id: str) -> Evaluation:
        doc = self._evaluations.find_by_id(tenant_id, evaluation_id)
        if doc is None:
            raise EvaluationNotFoundError(evaluation_id)
        return Evaluation.from_document(doc)

    def _readiness_reasons(
        self, tenant_id: str, evaluation: Evaluation, report_type: ReportType
    ) -> list[str]:
        if report_type == "decision_record":
            decision = self._decisions.get_or_none(tenant_id, evaluation.id)
            if decision is None or decision.status != "approved":
                return ["la decisión debe estar aprobada"]
            return []
        if report_type in _READINESS_GATED_BY_RESULTS:
            if evaluation.status not in ("evaluating", "completed"):
                return ["la evaluación debe estar en evaluación o completada"]
            return []
        # rfp_document, requirements_matrix, qna_summary - available any time
        # an Evaluation exists, live from draft data or from the published
        # EvaluationSnapshot once one exists.
        return []

    def readiness(
        self, tenant_id: str, evaluation_id: str, report_type: ReportType
    ) -> dict[str, Any]:
        evaluation = self._get_evaluation(tenant_id, evaluation_id)
        reasons = self._readiness_reasons(tenant_id, evaluation, report_type)
        return {
            "can_generate": not reasons,
            "reasons": reasons,
            "valid_formats": list(VALID_FORMATS_BY_TYPE[report_type]),
        }

    def request_generation(
        self,
        tenant_id: str,
        evaluation_id: str,
        *,
        report_type: ReportType,
        format: ReportFormat,
        actor: ActorContext,
    ) -> Report:
        evaluation = self._get_evaluation(tenant_id, evaluation_id)
        if format not in VALID_FORMATS_BY_TYPE[report_type]:
            raise InvalidReportFormatError(
                f"{format!r} is not valid for report_type {report_type!r}"
            )
        reasons = self._readiness_reasons(tenant_id, evaluation, report_type)
        if reasons:
            raise ReportNotReadyError("; ".join(reasons))

        report = Report.create(
            tenant_id=tenant_id,
            evaluation_id=evaluation_id,
            report_type=report_type,
            format=format,
            requested_by_membership_id=actor.membership_id,
            retention_days=self._retention_days,
        )
        self._reports.insert(tenant_id, report.to_document())
        self._message_bus.publish(
            JOB_TOPIC,
            {"tenant_id": tenant_id, "evaluation_id": evaluation_id, "report_id": report.id},
        )
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="report_generation_requested",
            resource_type="report",
            resource_id=report.id,
            evaluation_id=evaluation_id,
            metadata={"report_type": report_type, "format": format},
        )
        return report

    def get_report(self, tenant_id: str, evaluation_id: str, report_id: str) -> Report:
        doc = self._reports.find_by_id(tenant_id, report_id)
        if doc is None:
            raise ReportNotFoundError(report_id)
        report = Report.from_document(doc)
        if report.evaluation_id != evaluation_id:
            raise ReportNotFoundError(report_id)
        return report

    def list_reports(self, tenant_id: str, evaluation_id: str) -> list[Report]:
        self._get_evaluation(tenant_id, evaluation_id)
        return [
            Report.from_document(doc)
            for doc in self._reports.list_for_evaluation(tenant_id, evaluation_id)
        ]

    def get_download_url(
        self, tenant_id: str, evaluation_id: str, report_id: str, *, actor: ActorContext
    ) -> tuple[str, datetime]:
        report = self.get_report(tenant_id, evaluation_id, report_id)
        if report.status != "succeeded" or report.blob_key is None:
            raise ReportNotSucceededError(report_id)
        url = self._storage.generate_download_url(
            report.blob_key,
            expires_in_minutes=self._download_url_ttl_minutes,
            filename=f"{report.report_type}.{report.format}",
            content_type=report.content_type or "application/octet-stream",
        )
        expires_at = datetime.now(UTC) + timedelta(minutes=self._download_url_ttl_minutes)
        # Never the URL itself in metadata (same principle as
        # document_download_url_issued, Fase 16) - only that one was issued.
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="report_downloaded",
            resource_type="report",
            resource_id=report.id,
            evaluation_id=evaluation_id,
            metadata={"report_type": report.report_type},
        )
        return url, expires_at

    def _vendor_org_name(self, tenant_id: str, vendor_org_id: str) -> str:
        doc = self._vendor_orgs.find_by_id(tenant_id, vendor_org_id)
        return doc["name"] if doc else vendor_org_id

    def _render(
        self, tenant_id: str, evaluation_id: str, report_type: ReportType, format: ReportFormat
    ) -> tuple[bytes, str, dict[str, Any]]:
        evaluation = self._get_evaluation(tenant_id, evaluation_id)
        content_type = CONTENT_TYPE_BY_FORMAT[format]

        if report_type in ("rfp_document", "requirements_matrix"):
            snapshot_doc = self._evaluation_snapshots.find_by_evaluation_id(
                tenant_id, evaluation_id
            )
            snapshot = EvaluationSnapshot.from_document(snapshot_doc) if snapshot_doc else None
            snapshot_source_ref: dict[str, Any] = {
                "evaluation_snapshot_id": snapshot.snapshot_id if snapshot else None
            }
            if report_type == "rfp_document":
                document = assembly.assemble_rfp_document(evaluation, snapshot)
                content = (
                    pdf_renderer.render(document)
                    if format == "pdf"
                    else docx_renderer.render(document)
                )
            else:
                workbook = assembly.assemble_requirements_matrix(evaluation, snapshot)
                content = (
                    xlsx_renderer.render(workbook)
                    if format == "xlsx"
                    else csv_renderer.render(workbook)
                )
            return content, content_type, snapshot_source_ref

        if report_type in ("vendor_comparison", "scoring_detail", "risk_analysis"):
            results = self._scoring.get_results(tenant_id, evaluation_id)
            narrative_builders = {
                "vendor_comparison": assembly.assemble_vendor_comparison,
                "scoring_detail": assembly.assemble_scoring_detail,
                "risk_analysis": assembly.assemble_risk_analysis,
            }
            document = narrative_builders[report_type](evaluation, results)
            content = pdf_renderer.render(document)
            comparison_source_ref: dict[str, Any] = {
                "result_status": results["result_status"],
                "as_of": datetime.now(UTC).isoformat(),
            }
            return content, content_type, comparison_source_ref

        if report_type == "tco_breakdown":
            proposal_tco = []
            for proposal_doc in self._proposals.find_by_evaluation(tenant_id, evaluation_id):
                proposal = Proposal.from_document(proposal_doc)
                proposal_snapshot = proposal.current_snapshot
                if proposal_snapshot is None or proposal_snapshot.tco_result is None:
                    continue
                vendor_name = self._vendor_org_name(tenant_id, proposal.vendor_org_id)
                proposal_tco.append((vendor_name, proposal_snapshot.tco_result))
            workbook = assembly.assemble_tco_breakdown(evaluation, proposal_tco)
            content = (
                xlsx_renderer.render(workbook)
                if format == "xlsx"
                else csv_renderer.render(workbook)
            )
            tco_source_ref: dict[str, Any] = {"proposal_count": len(proposal_tco)}
            return content, content_type, tco_source_ref

        if report_type == "decision_record":
            decision_snapshot = self._decisions.get_snapshot(tenant_id, evaluation_id)
            document = assembly.assemble_decision_record(evaluation, decision_snapshot)
            content = pdf_renderer.render(document)
            decision_source_ref: dict[str, Any] = {
                "decision_snapshot_id": decision_snapshot.snapshot_id
            }
            return content, content_type, decision_source_ref

        # qna_summary - the only remaining ReportType value.
        questions = [
            Question.from_document(doc)
            for doc in self._qna.list_for_evaluation_as_buyer(tenant_id, evaluation_id)
        ]
        document = assembly.assemble_qna_summary(evaluation, questions)
        content = pdf_renderer.render(document)
        qna_source_ref: dict[str, Any] = {"question_count": len(questions)}
        return content, content_type, qna_source_ref

    def process_generation_job(self, tenant_id: str, evaluation_id: str, report_id: str) -> None:
        doc = self._reports.find_by_id(tenant_id, report_id)
        if doc is None:
            logger.error("report_not_found_for_job", extra={"report_id": report_id})
            return
        report = Report.from_document(doc)
        if report.status != "queued":
            # Idempotency guard (ADR 0005: every job must be retryable
            # idempotently) - a redelivered message for an already-processed
            # report is a no-op, not an error.
            return
        if not self._reports.transition_status(
            tenant_id, report_id, "queued", "running", {"started_at": datetime.now(UTC)}
        ):
            return

        try:
            content, content_type, source_ref = self._render(
                tenant_id, evaluation_id, report.report_type, report.format
            )
        except Exception as exc:  # noqa: BLE001 - any assembly/render failure lands the job in `failed`, never crashes the worker loop
            logger.error(
                "report_generation_failed",
                extra={"report_id": report_id, "error_type": type(exc).__name__},
                exc_info=True,
            )
            self._reports.transition_status(
                tenant_id,
                report_id,
                "running",
                "failed",
                {"error": str(exc), "completed_at": datetime.now(UTC)},
            )
            self._record_failure_audit(tenant_id, report, str(exc))
            return

        blob_key = report.blob_key_for()
        self._storage.upload(blob_key, content, content_type=content_type)
        self._reports.transition_status(
            tenant_id,
            report_id,
            "running",
            "succeeded",
            {
                "blob_key": blob_key,
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "content_type": content_type,
                "source_ref": source_ref,
                "completed_at": datetime.now(UTC),
            },
        )
        self._record_success_audit(tenant_id, report)

    def _resolve_requester(self, report: Report) -> ActorContext | None:
        """The worker process has no HTTP-resolved ActorContext of its own -
        same pattern as ai.service.AIService._resolve_requester: look up the
        job's original requester so the AuditEvent records a real actor, and
        skip the (best-effort) audit call entirely if that Membership no
        longer resolves."""
        try:
            return self._identity.resolve_actor_context(report.requested_by_membership_id)
        except ActorNotFoundError:
            logger.warning("report_requester_not_found", extra={"report_id": report.id})
            return None

    def _record_success_audit(self, tenant_id: str, report: Report) -> None:
        actor = self._resolve_requester(report)
        if actor is None:
            return
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="report_generation_succeeded",
            resource_type="report",
            resource_id=report.id,
            evaluation_id=report.evaluation_id,
            metadata={"report_type": report.report_type, "format": report.format},
        )

    def _record_failure_audit(self, tenant_id: str, report: Report, error: str) -> None:
        actor = self._resolve_requester(report)
        if actor is None:
            return
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="report_generation_failed",
            resource_type="report",
            resource_id=report.id,
            evaluation_id=report.evaluation_id,
            metadata={
                "report_type": report.report_type,
                "format": report.format,
                "error_type": error[:200],
            },
        )
