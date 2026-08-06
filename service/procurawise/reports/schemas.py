from datetime import datetime

from procurawise.reports.models import ReportFormat, ReportStatus, ReportType
from procurawise.shared.api_models import APIModel


class ReportCreateRequest(APIModel):
    report_type: ReportType
    format: ReportFormat


class ReportResponse(APIModel):
    id: str
    evaluation_id: str
    report_type: ReportType
    format: ReportFormat
    status: ReportStatus
    requested_by_membership_id: str
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None
    size_bytes: int | None


class ReportReadinessResponse(APIModel):
    can_generate: bool
    reasons: list[str]
    valid_formats: list[ReportFormat]


class ReportDownloadUrlResponse(APIModel):
    url: str
    expires_at: datetime
