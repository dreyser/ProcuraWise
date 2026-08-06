from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

# Fase 23 (backlog.md fila 23, spec S10) - the 8 deliverables, one Literal
# value each. A single generic `Report` entity discriminated by
# `report_type` (same pattern as AIExecution.use_case, Fase 13/18) rather
# than 8 separate models - the job lifecycle/persistence/download shape is
# identical across all 8, only the assembly+renderer differ.
ReportType = Literal[
    "rfp_document",
    "requirements_matrix",
    "vendor_comparison",
    "scoring_detail",
    "risk_analysis",
    "tco_breakdown",
    "decision_record",
    "qna_summary",
]

# ADR 0023: docx only ever pairs with rfp_document; pdf with the 5 other
# narrative types (+ rfp_document itself); xlsx/csv only with the 2 tabular
# types. Validated in service.py, not here (schemas describe shape, services
# validate business rules - same convention as the rest of this codebase).
ReportFormat = Literal["pdf", "xlsx", "csv", "docx"]

# Identical shape to AIExecutionStatus (Fase 13/18) - same job lifecycle.
ReportStatus = Literal["queued", "running", "succeeded", "failed"]


def new_id() -> str:
    return uuid4().hex


@dataclass(frozen=True)
class Report:
    """One record per generation request (never overwritten - "regenerar" is
    a brand new Report, same insert-only philosophy as AuditEvent/
    AIExecution). `source_ref` carries the traceability the spec demands
    ("version, fecha de corte, moneda/tipo de cambio, pesos, formula y
    advertencias") as a pointer to the snapshot(s) actually used - e.g.
    {"decision_snapshot_id": ...} or {"evaluation_snapshot_id": ...,
    "as_of": ...} - never a copy of the underlying data itself, which stays
    owned by its source module."""

    id: str
    tenant_id: str
    evaluation_id: str
    report_type: ReportType
    format: ReportFormat
    status: ReportStatus
    requested_by_membership_id: str
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None
    blob_key: str | None
    size_bytes: int | None
    sha256: str | None
    content_type: str | None
    source_ref: dict[str, Any] | None
    expires_at: datetime

    @staticmethod
    def create(
        *,
        tenant_id: str,
        evaluation_id: str,
        report_type: ReportType,
        format: ReportFormat,
        requested_by_membership_id: str,
        retention_days: int,
    ) -> "Report":
        now = datetime.now(UTC)
        return Report(
            id=new_id(),
            tenant_id=tenant_id,
            evaluation_id=evaluation_id,
            report_type=report_type,
            format=format,
            status="queued",
            requested_by_membership_id=requested_by_membership_id,
            requested_at=now,
            started_at=None,
            completed_at=None,
            error=None,
            blob_key=None,
            size_bytes=None,
            sha256=None,
            content_type=None,
            source_ref=None,
            expires_at=now + timedelta(days=retention_days),
        )

    def blob_key_for(self) -> str:
        """Deterministic, collision-free key - {tenant}/{evaluation}/{report_id}.{format},
        same directory-per-scope convention as documents.models.Document.build_blob_key."""
        return f"{self.tenant_id}/{self.evaluation_id}/{self.id}.{self.format}"

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "tenant_id": self.tenant_id,
            "evaluation_id": self.evaluation_id,
            "report_type": self.report_type,
            "format": self.format,
            "status": self.status,
            "requested_by_membership_id": self.requested_by_membership_id,
            "requested_at": self.requested_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "blob_key": self.blob_key,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "content_type": self.content_type,
            "source_ref": self.source_ref,
            "expires_at": self.expires_at,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "Report":
        return Report(
            id=doc["_id"],
            tenant_id=doc["tenant_id"],
            evaluation_id=doc["evaluation_id"],
            report_type=doc["report_type"],
            format=doc["format"],
            status=doc["status"],
            requested_by_membership_id=doc["requested_by_membership_id"],
            requested_at=doc["requested_at"],
            started_at=doc.get("started_at"),
            completed_at=doc.get("completed_at"),
            error=doc.get("error"),
            blob_key=doc.get("blob_key"),
            size_bytes=doc.get("size_bytes"),
            sha256=doc.get("sha256"),
            content_type=doc.get("content_type"),
            source_ref=doc.get("source_ref"),
            expires_at=doc["expires_at"],
        )


# Fase 23 - which formats are valid for which report_type (used by
# service.py to validate a creation request; also the single source of
# truth the frontend's format selector mirrors). rfp_document is the only
# type with two valid formats (spec S10: "Word y PDF").
VALID_FORMATS_BY_TYPE: dict[ReportType, tuple[ReportFormat, ...]] = {
    "rfp_document": ("pdf", "docx"),
    "requirements_matrix": ("xlsx", "csv"),
    "vendor_comparison": ("pdf",),
    "scoring_detail": ("pdf",),
    "risk_analysis": ("pdf",),
    "tco_breakdown": ("xlsx", "csv"),
    "decision_record": ("pdf",),
    "qna_summary": ("pdf",),
}

CONTENT_TYPE_BY_FORMAT: dict[ReportFormat, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
}
