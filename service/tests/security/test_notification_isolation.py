"""Fase 24 (plan S5.6): a Notification's sole authorized reader is its own
recipient_membership_id - this is enforced at the repository/service layer
(every query/mutation filters by the resolved actor's own membership_id,
never a client-supplied one), not via require_role. This needs its own
dedicated negative test, separate from ordinary tenant isolation: a
different Membership within the *same* tenant must not be able to read or
mark-read another recipient's Notification, in addition to the usual
cross-tenant 404s."""

import pytest

from procurawise.identity.models import Membership, User, VendorOrganization
from procurawise.identity.repository import (
    MembershipRepository,
    UserRepository,
    VendorOrganizationRepository,
)
from procurawise.notifications.dependencies import build_notification_service
from tests.conftest import (
    bearer_headers_for,
    tenant_ids,
    unique_actor_by_role,
    vendor_bearer_headers_for,
)

pytestmark = pytest.mark.docker


def _notify(
    mongo_test_settings, tenant_id: str, recipient_membership_id: str, resource_id: str
) -> None:
    service = build_notification_service(mongo_test_settings)
    service.notify(
        tenant_id,
        recipient_membership_id=recipient_membership_id,
        event="evaluation_completed",
        resource_type="evaluation",
        resource_id=resource_id,
        evaluation_id=resource_id,
        title="t",
        body="b",
    )


def _notification_id_for(
    mongo_test_settings, tenant_id: str, membership_id: str, resource_id: str
) -> str:
    service = build_notification_service(mongo_test_settings)
    items, _ = service.list_for_recipient(tenant_id, membership_id, limit=100)
    return next(n.id for n in items if n.resource_id == resource_id)


def _create_second_vendor_contact(mongo_test_db, tenant_id: str) -> tuple[str, str]:
    """A genuinely second vendor_contact Membership in the same tenant
    (different vendor org, different user) - mirrors
    tests/integration/test_proposal_reopen.py's _create_second_vendor. No
    agreements-accept needed here: require_vendor_context (unlike
    require_agreements_accepted-gated proposal/qna routes) doesn't require
    them."""
    users = UserRepository(mongo_test_db)
    vendor_orgs = VendorOrganizationRepository(mongo_test_db)
    memberships = MembershipRepository(mongo_test_db)

    user = User.create(display_name="Vendor Contact B", email="vendor.b.notifications@dev.local")
    users.insert(user.to_document())
    vendor_org = VendorOrganization.create(
        tenant_id=tenant_id, name="Proveedor Dos (notifications)"
    )
    vendor_orgs.insert(tenant_id, vendor_org.to_document())
    membership = Membership.create(
        tenant_id=tenant_id, user_id=user.id, role="vendor_contact", vendor_org_id=vendor_org.id
    )
    memberships.insert(membership.to_document())
    return vendor_org.id, membership.id


# --- buyer: /api/v1/notifications ---------------------------------------


def test_buyer_cannot_mark_read_a_notification_belonging_to_another_tenant(
    mongo_test_settings, mongo_test_db, seeded_actors, client
) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a = seeded_actors[(tenant_a, "evaluation_owner")]
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )

    _notify(mongo_test_settings, tenant_a, owner_a, "cross-tenant-mark-read")
    notification_id = _notification_id_for(
        mongo_test_settings, tenant_a, owner_a, "cross-tenant-mark-read"
    )

    response = client.patch(
        f"/api/v1/notifications/{notification_id}/read", headers=owner_b_headers
    )
    assert response.status_code == 404


def test_buyer_cannot_mark_read_a_notification_belonging_to_a_different_membership_same_tenant(
    mongo_test_settings, mongo_test_db, seeded_actors, client
) -> None:
    # unique_actor_by_role("vendor_contact") deterministically lands on the
    # tenant where the approver is a genuinely distinct user from the owner
    # (see tests/integration/test_notification_events_workflow.py for why).
    tenant_a, _vendor_contact = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_a = seeded_actors[(tenant_a, "evaluation_owner")]
    approver_a = seeded_actors[(tenant_a, "approver")]
    approver_headers = bearer_headers_for(approver_a, mongo_test_settings)

    _notify(mongo_test_settings, tenant_a, owner_a, "same-tenant-mark-read")
    notification_id = _notification_id_for(
        mongo_test_settings, tenant_a, owner_a, "same-tenant-mark-read"
    )

    response = client.patch(
        f"/api/v1/notifications/{notification_id}/read", headers=approver_headers
    )
    assert response.status_code == 404

    # The owner's own notification must remain untouched (still unread).
    owner_headers = bearer_headers_for(owner_a, mongo_test_settings)
    listing = client.get("/api/v1/notifications", headers=owner_headers).json()
    matching = next(n for n in listing["items"] if n["resource_id"] == "same-tenant-mark-read")
    assert matching["read_at"] is None


def test_buyer_list_never_returns_another_recipients_notification(
    mongo_test_settings, mongo_test_db, seeded_actors, client
) -> None:
    tenant_a, _vendor_contact = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_a = seeded_actors[(tenant_a, "evaluation_owner")]
    approver_a = seeded_actors[(tenant_a, "approver")]
    approver_headers = bearer_headers_for(approver_a, mongo_test_settings)

    _notify(mongo_test_settings, tenant_a, owner_a, "not-my-notification")

    listing = client.get("/api/v1/notifications", headers=approver_headers).json()
    assert all(n["resource_id"] != "not-my-notification" for n in listing["items"])


def test_vendor_contact_cannot_read_buyer_notifications_endpoints(
    client, seeded_actors, mongo_test_settings
) -> None:
    _tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    vendor_headers = bearer_headers_for(vendor_membership_id, mongo_test_settings)

    response = client.get("/api/v1/notifications", headers=vendor_headers)
    assert response.status_code == 403


# --- vendor: /api/v1/vendor-portal/notifications -------------------------


def test_vendor_cannot_mark_read_a_notification_belonging_to_another_tenant(
    mongo_test_settings, mongo_test_db, seeded_actors, client
) -> None:
    tenant_a, vendor_a = unique_actor_by_role(seeded_actors, "vendor_contact")
    tenants = tenant_ids(seeded_actors)
    tenant_b = next(t for t in tenants if t != tenant_a)
    # tenant_b never seeds its own vendor_contact - create a genuinely
    # distinct vendor_contact there to mint a real cross-tenant vendor token.
    _vendor_org_b, vendor_b = _create_second_vendor_contact(mongo_test_db, tenant_b)
    vendor_b_headers = vendor_bearer_headers_for(vendor_b, mongo_test_settings)

    _notify(mongo_test_settings, tenant_a, vendor_a, "cross-tenant-vendor-mark-read")
    notification_id = _notification_id_for(
        mongo_test_settings, tenant_a, vendor_a, "cross-tenant-vendor-mark-read"
    )

    response = client.patch(
        f"/api/v1/vendor-portal/notifications/{notification_id}/read", headers=vendor_b_headers
    )
    assert response.status_code == 404


def test_vendor_cannot_mark_read_a_notification_belonging_to_a_different_vendor_contact_same_tenant(
    mongo_test_settings, mongo_test_db, seeded_actors, client
) -> None:
    tenant_a, vendor_a = unique_actor_by_role(seeded_actors, "vendor_contact")
    _vendor_org_b, vendor_b = _create_second_vendor_contact(mongo_test_db, tenant_a)
    vendor_b_headers = vendor_bearer_headers_for(vendor_b, mongo_test_settings)

    _notify(mongo_test_settings, tenant_a, vendor_a, "same-tenant-vendor-mark-read")
    notification_id = _notification_id_for(
        mongo_test_settings, tenant_a, vendor_a, "same-tenant-vendor-mark-read"
    )

    response = client.patch(
        f"/api/v1/vendor-portal/notifications/{notification_id}/read", headers=vendor_b_headers
    )
    assert response.status_code == 404

    vendor_a_headers = vendor_bearer_headers_for(vendor_a, mongo_test_settings)
    listing = client.get("/api/v1/vendor-portal/notifications", headers=vendor_a_headers).json()
    matching = next(
        n for n in listing["items"] if n["resource_id"] == "same-tenant-vendor-mark-read"
    )
    assert matching["read_at"] is None


def test_buyer_cannot_read_vendor_notifications_endpoints(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _vendor_contact = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )

    # A buyer bearer token is a different token audience than a vendor
    # token - the vendor router rejects it outright (401), same as any
    # other vendor-portal route given a non-vendor token.
    response = client.get("/api/v1/vendor-portal/notifications", headers=owner_headers)
    assert response.status_code == 401
