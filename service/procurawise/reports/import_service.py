from procurawise.audit.service import AuditEventService
from procurawise.evaluations.exceptions import EvaluationNotFoundError, InvalidTransitionError
from procurawise.evaluations.models import Evaluation, Requirement
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.reports.exceptions import RequirementsImportError
from procurawise.reports.import_parsing import parse_requirements_file
from procurawise.reports.import_types import RequirementImportPreview
from procurawise.shared.context import ActorContext


class RequirementImportService:
    """Fase 23 (backlog.md fila 23: "import Excel/CSV con preview+mapeo").
    `confirm()` is a third producer of Requirement rows alongside manual
    entry (evaluations.service.add_requirement) and applying a
    KnowledgeTemplate (Fase 11) - all three converge on the same
    EvaluationRepository.add_requirements_bulk atomic write, never a
    separate write path of its own."""

    def __init__(self, evaluations: EvaluationRepository, audit: AuditEventService) -> None:
        self._evaluations = evaluations
        self._audit = audit

    def _get_draft_evaluation(self, tenant_id: str, evaluation_id: str) -> Evaluation:
        doc = self._evaluations.find_by_id(tenant_id, evaluation_id)
        if doc is None:
            raise EvaluationNotFoundError(evaluation_id)
        evaluation = Evaluation.from_document(doc)
        if evaluation.status != "draft":
            raise InvalidTransitionError(evaluation_id)
        return evaluation

    def preview(
        self, tenant_id: str, evaluation_id: str, *, filename: str, content: bytes
    ) -> RequirementImportPreview:
        self._get_draft_evaluation(tenant_id, evaluation_id)
        columns, rows, suggested_mapping = parse_requirements_file(filename, content)
        if not rows:
            raise RequirementsImportError("el archivo no tiene filas de datos")
        return RequirementImportPreview(
            columns=columns, rows=rows, suggested_mapping=suggested_mapping
        )

    def confirm(
        self,
        tenant_id: str,
        evaluation_id: str,
        requirements: list[Requirement],
        *,
        actor: ActorContext,
    ) -> list[Requirement]:
        if not requirements:
            raise RequirementsImportError("no hay requerimientos que importar")
        evaluation = self._get_draft_evaluation(tenant_id, evaluation_id)
        # display_order must be unique/sequential within the batch being
        # imported - the client assigns it per row (same contract as manual
        # add_requirement), never re-derived here.
        matched = self._evaluations.add_requirements_bulk(
            tenant_id,
            evaluation_id,
            [r.to_document() for r in requirements],
            evaluation.approval_invalidation_extra_set(),
        )
        if not matched:
            raise InvalidTransitionError(evaluation_id)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="requirements_import_confirmed",
            resource_type="evaluation",
            resource_id=evaluation_id,
            evaluation_id=evaluation_id,
            metadata={"count": len(requirements)},
        )
        return requirements
