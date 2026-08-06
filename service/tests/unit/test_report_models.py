"""Fase 23 - model-level coverage for Report: safe defaults on create(), and
a lossless to_document/from_document round trip."""

from datetime import UTC, datetime

from procurawise.reports.models import VALID_FORMATS_BY_TYPE, Report


def test_report_create_defaults_to_queued() -> None:
    report = Report.create(
        tenant_id="tenant-1",
        evaluation_id="eval-1",
        report_type="vendor_comparison",
        format="pdf",
        requested_by_membership_id="m-owner",
        retention_days=365,
    )
    assert report.status == "queued"
    assert report.blob_key is None
    assert report.error is None
    assert report.completed_at is None
    assert report.blob_key_for() == f"tenant-1/eval-1/{report.id}.pdf"


def test_report_document_round_trip_is_lossless() -> None:
    now = datetime.now(UTC)
    report = Report(
        id="report-1",
        tenant_id="tenant-1",
        evaluation_id="eval-1",
        report_type="tco_breakdown",
        format="xlsx",
        status="succeeded",
        requested_by_membership_id="m-owner",
        requested_at=now,
        started_at=now,
        completed_at=now,
        error=None,
        blob_key="tenant-1/eval-1/report-1.xlsx",
        size_bytes=1024,
        sha256="abc123",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        source_ref={"evaluation_snapshot_id": "snap-1"},
        expires_at=now,
    )
    restored = Report.from_document(report.to_document())
    assert restored == report


def test_report_document_round_trip_tolerates_missing_optional_keys() -> None:
    now = datetime.now(UTC)
    minimal_doc = {
        "_id": "report-1",
        "tenant_id": "tenant-1",
        "evaluation_id": "eval-1",
        "report_type": "qna_summary",
        "format": "pdf",
        "status": "queued",
        "requested_by_membership_id": "m-owner",
        "requested_at": now,
        "expires_at": now,
    }
    report = Report.from_document(minimal_doc)
    assert report.blob_key is None
    assert report.source_ref is None


def test_valid_formats_cover_all_eight_report_types() -> None:
    assert len(VALID_FORMATS_BY_TYPE) == 8
    assert VALID_FORMATS_BY_TYPE["rfp_document"] == ("pdf", "docx")
    assert VALID_FORMATS_BY_TYPE["vendor_comparison"] == ("pdf",)
    assert VALID_FORMATS_BY_TYPE["tco_breakdown"] == ("xlsx", "csv")
