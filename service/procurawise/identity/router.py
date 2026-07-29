from fastapi import APIRouter, Depends, HTTPException, Query

from procurawise.identity.dev_provider import (
    get_current_context,
    get_identity_service,
    require_dev_environment,
)
from procurawise.identity.repository import VendorOrganizationRepository
from procurawise.identity.schemas import (
    ActorContextResponse,
    DevActorSummary,
    VendorOrganizationListResponse,
    VendorOrganizationSummary,
)
from procurawise.identity.service import (
    IdentityService,
    InvalidVendorOrganizationCursorError,
    VendorOrganizationService,
)
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext, require_role
from procurawise.shared.mongo import get_database

router = APIRouter(tags=["identity"])

BUYER_READ_ROLES = ("evaluation_owner", "evaluator")
require_buyer_read = require_role(*BUYER_READ_ROLES)


def get_vendor_organization_service(
    settings: Settings = Depends(get_settings),
) -> VendorOrganizationService:
    db = get_database(settings)
    return VendorOrganizationService(VendorOrganizationRepository(db))


@router.get("/dev/actors", response_model=list[DevActorSummary])
def list_dev_actors(
    settings: Settings = Depends(get_settings),
    identity_service: IdentityService = Depends(get_identity_service),
) -> list[DevActorSummary]:
    require_dev_environment(settings)
    return [
        DevActorSummary(
            actor_id=context.membership_id,
            display_name=context.display_name,
            tenant_name=context.tenant_name,
            role=context.role,
            vendor_org_id=context.vendor_org_id,
        )
        for context in identity_service.list_dev_actors()
    ]


@router.get("/me", response_model=ActorContextResponse)
def get_me(context: ActorContext = Depends(get_current_context)) -> ActorContextResponse:
    return ActorContextResponse(
        membership_id=context.membership_id,
        user_id=context.user_id,
        tenant_id=context.tenant_id,
        tenant_name=context.tenant_name,
        role=context.role,
        vendor_org_id=context.vendor_org_id,
        display_name=context.display_name,
    )


@router.get("/vendor-organizations", response_model=VendorOrganizationListResponse)
def list_vendor_organizations(
    search: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    context: ActorContext = Depends(require_buyer_read),
    service: VendorOrganizationService = Depends(get_vendor_organization_service),
) -> VendorOrganizationListResponse:
    try:
        organizations, next_cursor = service.list_vendor_organizations(
            context.tenant_id, search=search, limit=limit, cursor=cursor
        )
    except InvalidVendorOrganizationCursorError:
        raise HTTPException(status_code=422, detail="invalid cursor") from None
    return VendorOrganizationListResponse(
        items=[VendorOrganizationSummary(id=org.id, name=org.name) for org in organizations],
        next_cursor=next_cursor,
    )
