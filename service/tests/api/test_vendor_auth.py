import concurrent.futures
from datetime import UTC, datetime, timedelta

import pytest

from tests.conftest import bearer_headers_for, unique_actor_by_role, vendor_bearer_headers_for

pytestmark = pytest.mark.docker


def _owner_headers(seeded_actors, mongo_test_settings, tenant_id: str) -> dict[str, str]:
    return bearer_headers_for(seeded_actors[(tenant_id, "evaluation_owner")], mongo_test_settings)


def _create_vendor_org(
    client, owner_headers, *, name="Proveedor Nuevo", email="new.vendor@dev.local"
):
    response = client.post(
        "/api/v1/vendor-organizations",
        json={"name": name, "contact_email": email, "contact_display_name": "New Vendor Contact"},
        headers=owner_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_owner_can_create_vendor_organization_and_invite_primary_contact(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = _owner_headers(seeded_actors, mongo_test_settings, tenant_a)

    body = _create_vendor_org(client, owner_headers)
    assert body["name"] == "Proveedor Nuevo"
    invitation = body["invitation"]
    assert invitation["email"] == "new.vendor@dev.local"
    assert invitation["invite_token"]
    assert invitation["invite_url"].endswith(f"?token={invitation['invite_token']}")


def test_non_owner_cannot_create_vendor_organization(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "vendor_contact")
    evaluator_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluator_functional")], mongo_test_settings
    )
    response = client.post(
        "/api/v1/vendor-organizations",
        json={
            "name": "x",
            "contact_email": "x@dev.local",
            "contact_display_name": "X",
        },
        headers=evaluator_headers,
    )
    assert response.status_code == 403


def test_vendor_contact_cannot_create_vendor_organization(
    client, seeded_actors, mongo_test_settings
) -> None:
    # Privilege escalation attempt: a real vendor JWT (token_use=
    # vendor_access) presented to a buyer-authenticated endpoint - rejected
    # at authentication (401), never even reaches the owner-only role check.
    _tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    vendor_headers = vendor_bearer_headers_for(vendor_membership_id, mongo_test_settings)
    response = client.post(
        "/api/v1/vendor-organizations",
        json={"name": "x", "contact_email": "x@dev.local", "contact_display_name": "X"},
        headers=vendor_headers,
    )
    assert response.status_code == 401


def test_extra_field_in_vendor_organization_create_is_rejected(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = _owner_headers(seeded_actors, mongo_test_settings, tenant_a)
    response = client.post(
        "/api/v1/vendor-organizations",
        json={
            "name": "x",
            "contact_email": "x@dev.local",
            "contact_display_name": "X",
            "tenant_id": "not-mine",
        },
        headers=owner_headers,
    )
    assert response.status_code == 422


def test_accept_invitation_with_invalid_token_returns_404(client) -> None:
    response = client.post(
        "/api/v1/vendor-auth/accept-invitation",
        json={"token": "this-token-does-not-exist", "password": "whatever-123"},
    )
    assert response.status_code == 404


def test_accept_invitation_extra_field_is_rejected(client) -> None:
    response = client.post(
        "/api/v1/vendor-auth/accept-invitation",
        json={"token": "x", "password": "whatever-123", "role": "evaluation_owner"},
    )
    assert response.status_code == 422


def test_accept_invitation_with_expired_token_returns_404(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = _owner_headers(seeded_actors, mongo_test_settings, tenant_a)
    body = _create_vendor_org(client, owner_headers, email="expired.vendor@dev.local")
    invitation_id = body["invitation"]["invitation_id"]
    token = body["invitation"]["invite_token"]

    mongo_test_db["vendor_invitations"].update_one(
        {"_id": invitation_id}, {"$set": {"expires_at": datetime.now(UTC) - timedelta(days=1)}}
    )

    response = client.post(
        "/api/v1/vendor-auth/accept-invitation",
        json={"token": token, "password": "whatever-123"},
    )
    assert response.status_code == 404


def test_accept_invitation_token_cannot_be_replayed(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = _owner_headers(seeded_actors, mongo_test_settings, tenant_a)
    body = _create_vendor_org(client, owner_headers, email="replay.vendor@dev.local")
    token = body["invitation"]["invite_token"]

    first = client.post(
        "/api/v1/vendor-auth/accept-invitation",
        json={"token": token, "password": "first-password-123"},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/vendor-auth/accept-invitation",
        json={"token": token, "password": "second-password-123"},
    )
    assert second.status_code == 404


def test_accept_invitation_concurrent_replay_only_one_wins(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = _owner_headers(seeded_actors, mongo_test_settings, tenant_a)
    body = _create_vendor_org(client, owner_headers, email="concurrent.vendor@dev.local")
    token = body["invitation"]["invite_token"]

    def _attempt() -> int:
        return client.post(
            "/api/v1/vendor-auth/accept-invitation",
            json={"token": token, "password": "concurrent-password-123"},
        ).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(lambda _: _attempt(), range(8)))

    assert statuses.count(200) == 1
    assert statuses.count(404) == 7


def test_revoked_invitation_cannot_be_accepted(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = _owner_headers(seeded_actors, mongo_test_settings, tenant_a)
    body = _create_vendor_org(client, owner_headers, email="revoked.vendor@dev.local")
    vendor_org_id = body["id"]
    invitation_id = body["invitation"]["invitation_id"]
    token = body["invitation"]["invite_token"]

    revoke = client.post(
        f"/api/v1/vendor-organizations/{vendor_org_id}/collaborators/{invitation_id}/revoke",
        headers=owner_headers,
    )
    assert revoke.status_code == 204

    response = client.post(
        "/api/v1/vendor-auth/accept-invitation",
        json={"token": token, "password": "whatever-123"},
    )
    assert response.status_code == 404


def test_revoking_already_accepted_invitation_returns_409(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = _owner_headers(seeded_actors, mongo_test_settings, tenant_a)
    body = _create_vendor_org(client, owner_headers, email="already-accepted@dev.local")
    vendor_org_id = body["id"]
    invitation_id = body["invitation"]["invitation_id"]
    token = body["invitation"]["invite_token"]

    accept = client.post(
        "/api/v1/vendor-auth/accept-invitation",
        json={"token": token, "password": "whatever-123"},
    )
    assert accept.status_code == 200

    revoke = client.post(
        f"/api/v1/vendor-organizations/{vendor_org_id}/collaborators/{invitation_id}/revoke",
        headers=owner_headers,
    )
    assert revoke.status_code == 409


def test_invite_collaborator_for_another_tenants_vendor_org_returns_404(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "vendor_contact")
    tenant_b = next(t for t, _role in seeded_actors if t != tenant_a)
    owner_a_headers = _owner_headers(seeded_actors, mongo_test_settings, tenant_a)
    owner_b_headers = _owner_headers(seeded_actors, mongo_test_settings, tenant_b)

    body = _create_vendor_org(client, owner_a_headers, email="tenant-a-only@dev.local")
    vendor_org_id = body["id"]

    response = client.post(
        f"/api/v1/vendor-organizations/{vendor_org_id}/collaborators",
        json={"contact_email": "intruder@dev.local", "contact_display_name": "Intruder"},
        headers=owner_b_headers,
    )
    assert response.status_code == 404

    list_response = client.get(
        f"/api/v1/vendor-organizations/{vendor_org_id}/collaborators", headers=owner_b_headers
    )
    assert list_response.status_code == 404


def test_collaborator_cannot_invite_another_collaborator(
    client, seeded_actors, mongo_test_settings
) -> None:
    # Privilege escalation: a vendor_contact (even a legitimate one, already
    # a collaborator on this exact org) has no path to the owner-only
    # invite endpoint - the buyer-authenticated router rejects the vendor
    # token at authentication, same as any other vendor-vs-buyer boundary.
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = _owner_headers(seeded_actors, mongo_test_settings, tenant_a)
    vendor_headers = vendor_bearer_headers_for(vendor_membership_id, mongo_test_settings)

    dev_headers = {"X-Dev-Membership-Id": vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=dev_headers).json()["vendor_org_id"]

    response = client.post(
        f"/api/v1/vendor-organizations/{vendor_org_id}/collaborators",
        json={"contact_email": "self-invited@dev.local", "contact_display_name": "Self Invited"},
        headers=vendor_headers,
    )
    assert response.status_code == 401
    # sanity check the owner-side endpoint itself works for this same org
    assert (
        client.get(
            f"/api/v1/vendor-organizations/{vendor_org_id}/collaborators", headers=owner_headers
        ).status_code
        == 200
    )


def test_vendor_login_with_wrong_password_returns_401(
    client, seeded_actors, mongo_test_settings
) -> None:
    response = client.post(
        "/api/v1/vendor-auth/login",
        json={"email": "vendor.a@dev.procurawise.local", "password": "not-the-real-password"},
    )
    assert response.status_code == 401


def test_vendor_login_with_unknown_email_returns_401(client) -> None:
    response = client.post(
        "/api/v1/vendor-auth/login",
        json={"email": "nobody@dev.local", "password": "whatever-123"},
    )
    assert response.status_code == 401


def test_buyer_password_cannot_log_into_vendor_auth(client) -> None:
    # A buyer email/password (DEV_BUYER_PASSWORD) has no vendor_contact
    # Membership at all - login collapses to the same generic 401 as any
    # other invalid-credentials case, never confirming "this email exists
    # but isn't a vendor".
    response = client.post(
        "/api/v1/vendor-auth/login",
        json={"email": "owner.a@dev.procurawise.local", "password": "dev-password-2026"},
    )
    assert response.status_code == 401


def test_invitation_token_and_hash_never_appear_in_audit_events(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = _owner_headers(seeded_actors, mongo_test_settings, tenant_a)
    body = _create_vendor_org(client, owner_headers, email="audit-check@dev.local")
    token = body["invitation"]["invite_token"]

    client.post(
        "/api/v1/vendor-auth/accept-invitation",
        json={"token": token, "password": "whatever-123"},
    )

    events = list(
        mongo_test_db["audit_events"].find(
            {
                "action": {
                    "$in": [
                        "vendor_organization_created",
                        "vendor_invitation_accepted",
                        "agreement_accepted",
                    ]
                }
            }
        )
    )
    assert events, "expected at least one audit event to have been recorded"
    for event in events:
        serialized = str(event)
        assert token not in serialized
        assert "token_hash" not in event.get("metadata", {})
