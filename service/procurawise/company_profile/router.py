from fastapi import APIRouter, Depends

from procurawise.company_profile.dependencies import build_company_profile_service
from procurawise.company_profile.models import CompanyProfile
from procurawise.company_profile.schemas import (
    CompanyProfileResponse,
    UpdateCompanyProfileRequest,
)
from procurawise.company_profile.service import CompanyProfileService
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext, require_role
from procurawise.shared.roles import COMPANY_PROFILE_ROLES

router = APIRouter(prefix="/company-profile", tags=["company-profile"])

require_company_profile_access = require_role(*COMPANY_PROFILE_ROLES)


def get_company_profile_service(
    settings: Settings = Depends(get_settings),
) -> CompanyProfileService:
    return build_company_profile_service(settings)


def _profile_response(profile: CompanyProfile) -> CompanyProfileResponse:
    return CompanyProfileResponse(
        legal_name=profile.legal_name,
        tax_id=profile.tax_id,
        address=profile.address,
        industry=profile.industry,
        website_url=profile.website_url,
        updated_at=profile.updated_at,
    )


@router.get("", response_model=CompanyProfileResponse)
def get_company_profile(
    context: ActorContext = Depends(require_company_profile_access),
    service: CompanyProfileService = Depends(get_company_profile_service),
) -> CompanyProfileResponse:
    return _profile_response(service.get_profile(context.tenant_id))


@router.put("", response_model=CompanyProfileResponse)
def update_company_profile(
    body: UpdateCompanyProfileRequest,
    context: ActorContext = Depends(require_company_profile_access),
    service: CompanyProfileService = Depends(get_company_profile_service),
) -> CompanyProfileResponse:
    profile = service.update_profile(
        context.tenant_id,
        actor=context,
        legal_name=body.legal_name,
        tax_id=body.tax_id,
        address=body.address,
        industry=body.industry,
        website_url=body.website_url,
    )
    return _profile_response(profile)
