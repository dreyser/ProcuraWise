from fastapi import APIRouter, Depends, HTTPException, Query

from procurawise.admin.context import PlatformAdminContext, require_platform_admin
from procurawise.admin.repository import PlatformAdminAccountRepository
from procurawise.admin.schemas import (
    AdminEvaluationListResponse,
    AdminEvaluationSummary,
    AdminLoginRequest,
    AdminTokenResponse,
)
from procurawise.admin.service import (
    AdminAuthService,
    AdminEvaluationService,
    InvalidAdminCredentialsError,
    InvalidAdminCursorError,
)
from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.service import AuditEventService
from procurawise.curated_sources.models import CuratedSource
from procurawise.curated_sources.repository import CuratedSourceRepository
from procurawise.curated_sources.schemas import (
    CreateCuratedSourceRequest,
    CuratedSourceListResponse,
    CuratedSourceResponse,
    UpdateCuratedSourceRequest,
)
from procurawise.curated_sources.service import CuratedSourceNotFoundError, CuratedSourceService
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.jwt_provider import create_admin_access_token
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.mongo import get_database

# Physically separate from every buyer/vendor router (CLAUDE.md §4: platform_admin
# routes stay in their own router, never mixed with buyer or vendor-portal ones).
router = APIRouter(prefix="/admin", tags=["admin"])

require_admin = require_platform_admin()


def get_curated_source_service(
    settings: Settings = Depends(get_settings),
) -> CuratedSourceService:
    return CuratedSourceService(CuratedSourceRepository(get_database(settings)))


def _curated_source_response(source: CuratedSource) -> CuratedSourceResponse:
    return CuratedSourceResponse(
        id=source.id,
        title=source.title,
        url=source.url,
        summary=source.summary,
        tags=source.tags,
        active=source.active,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


def get_admin_auth_service(settings: Settings = Depends(get_settings)) -> AdminAuthService:
    return AdminAuthService(PlatformAdminAccountRepository(get_database(settings)))


def get_admin_evaluation_service(
    settings: Settings = Depends(get_settings),
) -> AdminEvaluationService:
    db = get_database(settings)
    return AdminEvaluationService(
        evaluations=EvaluationRepository(db),
        audit=AuditEventService(AuditEventRepository(db), settings),
    )


@router.post("/auth/login", response_model=AdminTokenResponse)
def admin_login(
    body: AdminLoginRequest,
    settings: Settings = Depends(get_settings),
    service: AdminAuthService = Depends(get_admin_auth_service),
) -> AdminTokenResponse:
    try:
        account = service.authenticate(body.email, body.password)
    except InvalidAdminCredentialsError:
        raise HTTPException(status_code=401, detail="invalid credentials") from None
    token, expires_in = create_admin_access_token(account.id, account.display_name, settings)
    return AdminTokenResponse(
        access_token=token,
        expires_in=expires_in,
        admin_id=account.id,
        display_name=account.display_name,
    )


@router.get("/evaluations", response_model=AdminEvaluationListResponse)
def list_evaluations_across_tenants(
    reason: str = Query(..., min_length=3),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    admin: PlatformAdminContext = Depends(require_admin),
    service: AdminEvaluationService = Depends(get_admin_evaluation_service),
) -> AdminEvaluationListResponse:
    try:
        evaluations, next_cursor = service.list_evaluations_across_tenants(
            reason=reason,
            limit=limit,
            cursor=cursor,
            admin_id=admin.admin_id,
            display_name=admin.display_name,
        )
    except InvalidAdminCursorError:
        raise HTTPException(status_code=422, detail="invalid cursor") from None
    return AdminEvaluationListResponse(
        items=[
            AdminEvaluationSummary(
                id=e.id,
                tenant_id=e.tenant_id,
                name=e.name,
                status=e.status,
                created_at=e.created_at,
            )
            for e in evaluations
        ],
        next_cursor=next_cursor,
    )


# Fase 14 (ADR 0011): minimal CuratedSourceProvider content management.
# platform_admin-only, no dedicated frontend screen this phase (founder
# decision, Fase 14 planning) - managed via this API directly.


@router.post("/curated-sources", response_model=CuratedSourceResponse, status_code=201)
def create_curated_source(
    body: CreateCuratedSourceRequest,
    admin: PlatformAdminContext = Depends(require_admin),
    service: CuratedSourceService = Depends(get_curated_source_service),
) -> CuratedSourceResponse:
    source = service.create(
        title=body.title,
        url=body.url,
        summary=body.summary,
        tags=body.tags,
        admin_id=admin.admin_id,
    )
    return _curated_source_response(source)


@router.get("/curated-sources", response_model=CuratedSourceListResponse)
def list_curated_sources(
    admin: PlatformAdminContext = Depends(require_admin),
    service: CuratedSourceService = Depends(get_curated_source_service),
) -> CuratedSourceListResponse:
    return CuratedSourceListResponse(
        items=[_curated_source_response(source) for source in service.list_all()]
    )


@router.patch("/curated-sources/{source_id}", response_model=CuratedSourceResponse)
def update_curated_source(
    source_id: str,
    body: UpdateCuratedSourceRequest,
    admin: PlatformAdminContext = Depends(require_admin),
    service: CuratedSourceService = Depends(get_curated_source_service),
) -> CuratedSourceResponse:
    try:
        source = service.update(
            source_id,
            title=body.title,
            url=body.url,
            summary=body.summary,
            tags=body.tags,
            admin_id=admin.admin_id,
        )
    except CuratedSourceNotFoundError:
        raise HTTPException(status_code=404) from None
    return _curated_source_response(source)


@router.post("/curated-sources/{source_id}/activate", response_model=CuratedSourceResponse)
def activate_curated_source(
    source_id: str,
    admin: PlatformAdminContext = Depends(require_admin),
    service: CuratedSourceService = Depends(get_curated_source_service),
) -> CuratedSourceResponse:
    try:
        source = service.activate(source_id, admin_id=admin.admin_id)
    except CuratedSourceNotFoundError:
        raise HTTPException(status_code=404) from None
    return _curated_source_response(source)


@router.post("/curated-sources/{source_id}/deactivate", response_model=CuratedSourceResponse)
def deactivate_curated_source(
    source_id: str,
    admin: PlatformAdminContext = Depends(require_admin),
    service: CuratedSourceService = Depends(get_curated_source_service),
) -> CuratedSourceResponse:
    try:
        source = service.deactivate(source_id, admin_id=admin.admin_id)
    except CuratedSourceNotFoundError:
        raise HTTPException(status_code=404) from None
    return _curated_source_response(source)
