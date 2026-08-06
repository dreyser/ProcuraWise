from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from procurawise.evaluations.exceptions import EvaluationNotFoundError
from procurawise.reports.dependencies import build_report_service
from procurawise.reports.exceptions import (
    InvalidReportFormatError,
    ReportNotFoundError,
    ReportNotReadyError,
    ReportNotSucceededError,
)
from procurawise.reports.models import Report, ReportType
from procurawise.reports.schemas import (
    ReportCreateRequest,
    ReportDownloadUrlResponse,
    ReportReadinessResponse,
    ReportResponse,
)
from procurawise.reports.service import ReportService
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext, require_role
from procurawise.shared.roles import BUYER_READ_ROLES, OWNER_ONLY

router = APIRouter(prefix="/evaluations/{evaluation_id}/reports", tags=["reports"])

require_buyer_read = require_role(*BUYER_READ_ROLES)
require_owner = require_role(*OWNER_ONLY)


def get_report_service(settings: Settings = Depends(get_settings)) -> ReportService:
    return build_report_service(settings)


def _report_response(report: Report) -> ReportResponse:
    return ReportResponse(
        id=report.id,
        evaluation_id=report.evaluation_id,
        report_type=report.report_type,
        format=report.format,
        status=report.status,
        requested_by_membership_id=report.requested_by_membership_id,
        requested_at=report.requested_at,
        started_at=report.started_at,
        completed_at=report.completed_at,
        error=report.error,
        size_bytes=report.size_bytes,
    )


@router.get("", response_model=list[ReportResponse])
def list_reports(
    evaluation_id: str,
    context: ActorContext = Depends(require_buyer_read),
    service: ReportService = Depends(get_report_service),
) -> list[ReportResponse]:
    try:
        reports = service.list_reports(context.tenant_id, evaluation_id)
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    return [_report_response(r) for r in reports]


@router.get("/readiness", response_model=ReportReadinessResponse)
def get_readiness(
    evaluation_id: str,
    report_type: Annotated[ReportType, Query()],
    context: ActorContext = Depends(require_buyer_read),
    service: ReportService = Depends(get_report_service),
) -> ReportReadinessResponse:
    try:
        readiness = service.readiness(context.tenant_id, evaluation_id, report_type)
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    return ReportReadinessResponse(**readiness)


@router.post("", response_model=ReportResponse, status_code=201)
def create_report(
    evaluation_id: str,
    body: ReportCreateRequest,
    context: ActorContext = Depends(require_owner),
    service: ReportService = Depends(get_report_service),
) -> ReportResponse:
    try:
        report = service.request_generation(
            context.tenant_id,
            evaluation_id,
            report_type=body.report_type,
            format=body.format,
            actor=context,
        )
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidReportFormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except ReportNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return _report_response(report)


@router.get("/{report_id}", response_model=ReportResponse)
def get_report(
    evaluation_id: str,
    report_id: str,
    context: ActorContext = Depends(require_buyer_read),
    service: ReportService = Depends(get_report_service),
) -> ReportResponse:
    try:
        report = service.get_report(context.tenant_id, evaluation_id, report_id)
    except ReportNotFoundError:
        raise HTTPException(status_code=404) from None
    return _report_response(report)


@router.get("/{report_id}/download-url", response_model=ReportDownloadUrlResponse)
def get_download_url(
    evaluation_id: str,
    report_id: str,
    context: ActorContext = Depends(require_buyer_read),
    service: ReportService = Depends(get_report_service),
) -> ReportDownloadUrlResponse:
    try:
        url, expires_at = service.get_download_url(
            context.tenant_id, evaluation_id, report_id, actor=context
        )
    except ReportNotFoundError:
        raise HTTPException(status_code=404) from None
    except ReportNotSucceededError:
        raise HTTPException(status_code=409, detail="report has not succeeded yet") from None
    return ReportDownloadUrlResponse(url=url, expires_at=expires_at)
