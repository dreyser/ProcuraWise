import hashlib
import secrets
from datetime import UTC, datetime
from typing import Any

from procurawise.audit.service import AuditEventService
from procurawise.identity.jwt_provider import create_vendor_access_token
from procurawise.identity.models import Membership, User, VendorInvitation, VendorOrganization
from procurawise.identity.passwords import hash_password, verify_password
from procurawise.identity.repository import (
    MembershipRepository,
    UserRepository,
    VendorInvitationRepository,
    VendorOrganizationRepository,
)
from procurawise.identity.service import IdentityService
from procurawise.shared.config import Settings
from procurawise.shared.context import ActorContext


class VendorOrganizationNotFoundError(Exception):
    """No VendorOrganization exists for this id within the caller's tenant."""


class VendorInvitationNotFoundError(Exception):
    """No VendorInvitation exists for this id within the caller's tenant."""


class VendorInvitationNotRevocableError(Exception):
    """The invitation is no longer `pending` (already accepted or revoked)."""


class VendorInvitationInvalidError(Exception):
    """The token does not resolve to a redeemable (pending, unexpired)
    invitation. Deliberately a single exception for every reason - invalid,
    expired, already used, revoked, and raced-by-a-concurrent-redemption of
    the same token all collapse to it, so the HTTP layer always returns the
    same generic 404 without confirming which case applies (no
    enumeration signal)."""


class InvalidVendorCredentialsError(Exception):
    """Generic vendor login failure - never distinguished between "no such
    email", "email has no vendor_contact membership", and "wrong
    password"."""


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class VendorAuthService:
    """Fase 15: owns creation of vendor organizations/collaborators (always
    buyer-initiated - founder decision D1, never vendor self-service) and
    redemption of the resulting invitation into a real vendor session
    (founder decision D2: org-level access, no evaluation_id scoping - a
    vendor_contact's Membership.vendor_org_id is the sole scope, exactly as
    it already is for the interim dev-header mechanism it replaces)."""

    def __init__(
        self,
        users: UserRepository,
        memberships: MembershipRepository,
        vendor_orgs: VendorOrganizationRepository,
        invitations: VendorInvitationRepository,
        identity_service: IdentityService,
        audit: AuditEventService,
        settings: Settings,
    ) -> None:
        self._users = users
        self._memberships = memberships
        self._vendor_orgs = vendor_orgs
        self._invitations = invitations
        self._identity_service = identity_service
        self._audit = audit
        self._settings = settings

    def _invite_contact(
        self,
        tenant_id: str,
        vendor_org_id: str,
        contact_email: str,
        contact_display_name: str,
        invited_by_membership_id: str,
    ) -> tuple[Membership, VendorInvitation, str]:
        user_doc = self._users.find_by_email(contact_email)
        user = User.from_document(user_doc) if user_doc is not None else None
        if user is None:
            user = User.create(display_name=contact_display_name, email=contact_email)
            self._users.insert(user.to_document())

        existing_membership = self._memberships.find_one_for(
            tenant_id, user.id, "vendor_contact", vendor_org_id
        )
        if existing_membership is not None:
            membership = Membership.from_document(existing_membership)
        else:
            membership = Membership.create(
                tenant_id=tenant_id,
                user_id=user.id,
                role="vendor_contact",
                vendor_org_id=vendor_org_id,
            )
            self._memberships.insert(membership.to_document())

        raw_token = secrets.token_urlsafe(32)
        invitation = VendorInvitation.create(
            tenant_id=tenant_id,
            vendor_org_id=vendor_org_id,
            membership_id=membership.id,
            email=contact_email,
            token_hash=_hash_token(raw_token),
            invited_by_membership_id=invited_by_membership_id,
            ttl_days=self._settings.vendor_invitation_ttl_days,
        )
        self._invitations.insert(tenant_id, invitation.to_document())
        return membership, invitation, raw_token

    def create_vendor_organization(
        self,
        tenant_id: str,
        name: str,
        contact_email: str,
        contact_display_name: str,
        *,
        actor: ActorContext,
    ) -> tuple[VendorOrganization, Membership, VendorInvitation, str]:
        vendor_org = VendorOrganization.create(tenant_id=tenant_id, name=name)
        self._vendor_orgs.insert(tenant_id, vendor_org.to_document())
        membership, invitation, raw_token = self._invite_contact(
            tenant_id, vendor_org.id, contact_email, contact_display_name, actor.membership_id
        )
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="vendor_organization_created",
            resource_type="vendor_organization",
            resource_id=vendor_org.id,
            metadata={"name": name, "invited_membership_id": membership.id},
        )
        return vendor_org, membership, invitation, raw_token

    def invite_collaborator(
        self,
        tenant_id: str,
        vendor_org_id: str,
        contact_email: str,
        contact_display_name: str,
        *,
        actor: ActorContext,
    ) -> tuple[Membership, VendorInvitation, str]:
        vendor_org_doc = self._vendor_orgs.find_by_id(tenant_id, vendor_org_id)
        if vendor_org_doc is None:
            raise VendorOrganizationNotFoundError(vendor_org_id)
        membership, invitation, raw_token = self._invite_contact(
            tenant_id, vendor_org_id, contact_email, contact_display_name, actor.membership_id
        )
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="vendor_collaborator_invited",
            resource_type="vendor_organization",
            resource_id=vendor_org_id,
            metadata={"invited_membership_id": membership.id},
        )
        return membership, invitation, raw_token

    def list_collaborators(self, tenant_id: str, vendor_org_id: str) -> list[dict[str, Any]]:
        vendor_org_doc = self._vendor_orgs.find_by_id(tenant_id, vendor_org_id)
        if vendor_org_doc is None:
            raise VendorOrganizationNotFoundError(vendor_org_id)
        return self._invitations.find_by_vendor_org(tenant_id, vendor_org_id)

    def revoke_invitation(
        self, tenant_id: str, vendor_org_id: str, invitation_id: str, *, actor: ActorContext
    ) -> None:
        invitation_doc = self._invitations.find_by_id(tenant_id, invitation_id)
        if invitation_doc is None or invitation_doc["vendor_org_id"] != vendor_org_id:
            raise VendorInvitationNotFoundError(invitation_id)
        won = self._invitations.try_revoke(tenant_id, invitation_id)
        if not won:
            raise VendorInvitationNotRevocableError(invitation_id)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="vendor_invitation_revoked",
            resource_type="vendor_organization",
            resource_id=vendor_org_id,
            metadata={"invitation_id": invitation_id},
        )

    def accept_invitation(self, token: str, password: str) -> tuple[ActorContext, str, int]:
        token_hash = _hash_token(token)
        invitation_doc = self._invitations.find_by_token_hash_unscoped(token_hash)
        if invitation_doc is None:
            raise VendorInvitationInvalidError()
        invitation = VendorInvitation.from_document(invitation_doc)

        now = datetime.now(UTC)
        won = self._invitations.try_accept(invitation.tenant_id, invitation.id, now)
        if not won:
            raise VendorInvitationInvalidError()

        membership_doc = self._memberships.find_by_id_and_tenant(
            invitation.membership_id, invitation.tenant_id
        )
        if membership_doc is None:
            raise VendorInvitationInvalidError()
        membership = Membership.from_document(membership_doc)

        self._users.update_password(membership.user_id, hash_password(password))

        context = self._identity_service.resolve_actor_context(membership.id)
        self._audit.record(
            tenant_id=invitation.tenant_id,
            actor=context,
            action="vendor_invitation_accepted",
            resource_type="vendor_organization",
            resource_id=invitation.vendor_org_id,
            metadata={"invitation_id": invitation.id},
        )
        access_token, expires_in = create_vendor_access_token(context, self._settings)
        return context, access_token, expires_in

    def login(self, email: str, password: str) -> tuple[ActorContext, str, int]:
        user_doc = self._users.find_by_email(email)
        user = User.from_document(user_doc) if user_doc is not None else None
        if (
            user is None
            or user.password_hash is None
            or not verify_password(password, user.password_hash)
        ):
            raise InvalidVendorCredentialsError()

        vendor_memberships = [
            Membership.from_document(doc)
            for doc in self._memberships.find_all_for_user(user.id)
            if doc["role"] == "vendor_contact"
        ]
        if not vendor_memberships:
            raise InvalidVendorCredentialsError()
        # Deterministic pick when a person somehow holds vendor_contact
        # memberships for more than one vendor organization (rare - a single
        # real vendor company per person is the overwhelmingly common case).
        # Fase 15 planning accepted this as a documented simplification
        # rather than building a membership-selection screen for an edge
        # case with no product requirement behind it.
        membership = min(vendor_memberships, key=lambda m: m.created_at)

        context = self._identity_service.resolve_actor_context(membership.id)
        access_token, expires_in = create_vendor_access_token(context, self._settings)
        return context, access_token, expires_in
