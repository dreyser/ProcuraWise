from fastapi import APIRouter, Depends

from procurawise.identity.dev_provider import (
    get_current_context,
    get_identity_service,
    require_dev_environment,
)
from procurawise.identity.schemas import ActorContextResponse, DevActorSummary
from procurawise.identity.service import IdentityService
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext

router = APIRouter(tags=["identity"])


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
