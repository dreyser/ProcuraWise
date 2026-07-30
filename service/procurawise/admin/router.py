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
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.jwt_provider import create_admin_access_token
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.mongo import get_database

# Physically separate from every buyer/vendor router (CLAUDE.md §4: platform_admin
# routes stay in their own router, never mixed with buyer or vendor-portal ones).
router = APIRouter(prefix="/admin", tags=["admin"])

require_admin = require_platform_admin()


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
