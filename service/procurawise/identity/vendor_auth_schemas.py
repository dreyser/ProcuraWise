from datetime import datetime

from procurawise.identity.models import VendorInvitationStatus
from procurawise.identity.schemas import ActorContextResponse
from procurawise.shared.api_models import APIModel


class VendorOrganizationCreateRequest(APIModel):
    name: str
    contact_email: str
    contact_display_name: str


class CollaboratorInviteRequest(APIModel):
    contact_email: str
    contact_display_name: str


class VendorInvitationResponse(APIModel):
    """`invite_token`/`invite_url` are shown exactly once, in this response -
    never logged, never persisted in plaintext anywhere (only its SHA-256
    digest is kept, see identity.models.VendorInvitation.token_hash), and
    never re-derivable after this call returns. The authenticated
    evaluation_owner who made this request is responsible for relaying the
    link to the vendor contact through whatever channel they choose - there
    is no automated email sending yet (that is Fase 24's explicit scope, not
    this one's)."""

    invitation_id: str
    membership_id: str
    email: str
    invite_token: str
    invite_url: str
    expires_at: datetime


class VendorOrganizationCreatedResponse(APIModel):
    id: str
    name: str
    invitation: VendorInvitationResponse


class CollaboratorSummaryResponse(APIModel):
    invitation_id: str
    membership_id: str
    email: str
    status: VendorInvitationStatus
    invited_at: datetime
    accepted_at: datetime | None


class CollaboratorListResponse(APIModel):
    items: list[CollaboratorSummaryResponse]


class AcceptInvitationRequest(APIModel):
    token: str
    password: str


class VendorLoginRequest(APIModel):
    email: str
    password: str


class VendorTokenResponse(APIModel):
    access_token: str
    expires_in: int
    actor: ActorContextResponse
