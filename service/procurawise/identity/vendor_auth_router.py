import logging

from fastapi import APIRouter, Depends, HTTPException

from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.service import AuditEventService
from procurawise.identity.repository import (
    MembershipRepository,
    TenantRepository,
    UserRepository,
    VendorInvitationRepository,
    VendorOrganizationRepository,
)
from procurawise.identity.schemas import ActorContextResponse
from procurawise.identity.service import IdentityService
from procurawise.identity.vendor_auth_schemas import (
    AcceptInvitationRequest,
    CollaboratorInviteRequest,
    CollaboratorListResponse,
    CollaboratorSummaryResponse,
    VendorInvitationResponse,
    VendorLoginRequest,
    VendorOrganizationCreatedResponse,
    VendorOrganizationCreateRequest,
    VendorTokenResponse,
)
from procurawise.identity.vendor_auth_service import (
    InvalidVendorCredentialsError,
    VendorAuthService,
    VendorInvitationInvalidError,
    VendorInvitationNotFoundError,
    VendorInvitationNotRevocableError,
    VendorOrganizationNotFoundError,
)
from procurawise.notifications.dependencies import build_notification_service
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext, require_role
from procurawise.shared.mongo import get_database
from procurawise.shared.roles import OWNER_ONLY

logger = logging.getLogger("procurawise.identity.vendor_auth")

# Buyer-authenticated: creating a vendor organization or inviting a
# collaborator is always initiated by the comprador (Fase 15 planning
# decision D1) - never a vendor self-service action, so this stays
# owner-only, same restriction as evaluations.router's link_vendor.
vendor_organizations_router = APIRouter(prefix="/vendor-organizations", tags=["identity"])

# Public: a vendor contact has no account (and therefore no JWT of any kind)
# until they redeem an invitation or log in for the first time - mirrors
# identity.auth_router's POST /auth/login being unauthenticated too.
vendor_auth_router = APIRouter(prefix="/vendor-auth", tags=["vendor-auth"])

require_owner = require_role(*OWNER_ONLY)


def get_vendor_auth_service(settings: Settings = Depends(get_settings)) -> VendorAuthService:
    db = get_database(settings)
    identity_service = IdentityService(
        tenants=TenantRepository(db),
        users=UserRepository(db),
        memberships=MembershipRepository(db),
    )
    return VendorAuthService(
        users=UserRepository(db),
        memberships=MembershipRepository(db),
        vendor_orgs=VendorOrganizationRepository(db),
        invitations=VendorInvitationRepository(db),
        identity_service=identity_service,
        audit=AuditEventService(AuditEventRepository(db), settings),
        notifications=build_notification_service(settings),
        settings=settings,
    )


def _invite_url(settings: Settings, raw_token: str) -> str:
    return f"{settings.frontend_base_url}/vendor/accept-invitation?token={raw_token}"


@vendor_organizations_router.post(
    "", response_model=VendorOrganizationCreatedResponse, status_code=201
)
def create_vendor_organization(
    body: VendorOrganizationCreateRequest,
    context: ActorContext = Depends(require_owner),
    service: VendorAuthService = Depends(get_vendor_auth_service),
    settings: Settings = Depends(get_settings),
) -> VendorOrganizationCreatedResponse:
    vendor_org, membership, invitation, raw_token = service.create_vendor_organization(
        context.tenant_id,
        body.name,
        body.contact_email,
        body.contact_display_name,
        actor=context,
    )
    logger.info(
        "vendor_invitation_created",
        extra={
            "tenant_id": context.tenant_id,
            "vendor_org_id": vendor_org.id,
            "invitation_id": invitation.id,
            "invited_email": body.contact_email,
        },
    )
    return VendorOrganizationCreatedResponse(
        id=vendor_org.id,
        name=vendor_org.name,
        invitation=VendorInvitationResponse(
            invitation_id=invitation.id,
            membership_id=membership.id,
            email=invitation.email,
            invite_token=raw_token,
            invite_url=_invite_url(settings, raw_token),
            expires_at=invitation.expires_at,
        ),
    )


@vendor_organizations_router.post(
    "/{vendor_org_id}/collaborators", response_model=VendorInvitationResponse, status_code=201
)
def invite_collaborator(
    vendor_org_id: str,
    body: CollaboratorInviteRequest,
    context: ActorContext = Depends(require_owner),
    service: VendorAuthService = Depends(get_vendor_auth_service),
    settings: Settings = Depends(get_settings),
) -> VendorInvitationResponse:
    try:
        membership, invitation, raw_token = service.invite_collaborator(
            context.tenant_id,
            vendor_org_id,
            body.contact_email,
            body.contact_display_name,
            actor=context,
        )
    except VendorOrganizationNotFoundError:
        raise HTTPException(status_code=404) from None
    logger.info(
        "vendor_invitation_created",
        extra={
            "tenant_id": context.tenant_id,
            "vendor_org_id": vendor_org_id,
            "invitation_id": invitation.id,
            "invited_email": body.contact_email,
        },
    )
    return VendorInvitationResponse(
        invitation_id=invitation.id,
        membership_id=membership.id,
        email=invitation.email,
        invite_token=raw_token,
        invite_url=f"{settings.frontend_base_url}/vendor/accept-invitation?token={raw_token}",
        expires_at=invitation.expires_at,
    )


@vendor_organizations_router.get(
    "/{vendor_org_id}/collaborators", response_model=CollaboratorListResponse
)
def list_collaborators(
    vendor_org_id: str,
    context: ActorContext = Depends(require_owner),
    service: VendorAuthService = Depends(get_vendor_auth_service),
) -> CollaboratorListResponse:
    try:
        invitations = service.list_collaborators(context.tenant_id, vendor_org_id)
    except VendorOrganizationNotFoundError:
        raise HTTPException(status_code=404) from None
    return CollaboratorListResponse(
        items=[
            CollaboratorSummaryResponse(
                invitation_id=doc["_id"],
                membership_id=doc["membership_id"],
                email=doc["email"],
                status=doc["status"],
                invited_at=doc["created_at"],
                accepted_at=doc.get("accepted_at"),
            )
            for doc in invitations
        ]
    )


@vendor_organizations_router.post(
    "/{vendor_org_id}/collaborators/{invitation_id}/revoke", status_code=204
)
def revoke_collaborator_invitation(
    vendor_org_id: str,
    invitation_id: str,
    context: ActorContext = Depends(require_owner),
    service: VendorAuthService = Depends(get_vendor_auth_service),
) -> None:
    try:
        service.revoke_invitation(context.tenant_id, vendor_org_id, invitation_id, actor=context)
    except VendorInvitationNotFoundError:
        raise HTTPException(status_code=404) from None
    except VendorInvitationNotRevocableError:
        raise HTTPException(status_code=409, detail="invitation is not pending") from None


@vendor_auth_router.post("/accept-invitation", response_model=VendorTokenResponse)
def accept_invitation(
    body: AcceptInvitationRequest,
    service: VendorAuthService = Depends(get_vendor_auth_service),
) -> VendorTokenResponse:
    try:
        context, access_token, expires_in = service.accept_invitation(body.token, body.password)
    except VendorInvitationInvalidError:
        raise HTTPException(status_code=404) from None
    return VendorTokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        actor=ActorContextResponse(
            membership_id=context.membership_id,
            user_id=context.user_id,
            tenant_id=context.tenant_id,
            tenant_name=context.tenant_name,
            role=context.role,
            vendor_org_id=context.vendor_org_id,
            display_name=context.display_name,
        ),
    )


@vendor_auth_router.post("/login", response_model=VendorTokenResponse)
def vendor_login(
    body: VendorLoginRequest,
    service: VendorAuthService = Depends(get_vendor_auth_service),
) -> VendorTokenResponse:
    try:
        context, access_token, expires_in = service.login(body.email, body.password)
    except InvalidVendorCredentialsError:
        raise HTTPException(status_code=401, detail="invalid credentials") from None
    return VendorTokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        actor=ActorContextResponse(
            membership_id=context.membership_id,
            user_id=context.user_id,
            tenant_id=context.tenant_id,
            tenant_name=context.tenant_name,
            role=context.role,
            vendor_org_id=context.vendor_org_id,
            display_name=context.display_name,
        ),
    )
