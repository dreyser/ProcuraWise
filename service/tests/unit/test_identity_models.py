from datetime import UTC, datetime

import pytest

from procurawise.identity.models import Membership, OidcIdentity, Role, User


def test_vendor_contact_membership_requires_vendor_org_id() -> None:
    with pytest.raises(ValueError, match="vendor_org_id"):
        Membership.create(tenant_id="t", user_id="u", role="vendor_contact", vendor_org_id=None)


def test_non_vendor_membership_rejects_vendor_org_id() -> None:
    with pytest.raises(ValueError, match="vendor_contact"):
        Membership.create(tenant_id="t", user_id="u", role="evaluation_owner", vendor_org_id="v")


def test_vendor_contact_membership_with_vendor_org_id_succeeds() -> None:
    membership = Membership.create(
        tenant_id="t", user_id="u", role="vendor_contact", vendor_org_id="v"
    )
    assert membership.role == "vendor_contact"
    assert membership.vendor_org_id == "v"


def test_evaluation_owner_membership_without_vendor_org_id_succeeds() -> None:
    membership = Membership.create(tenant_id="t", user_id="u", role="evaluation_owner")
    assert membership.vendor_org_id is None


@pytest.mark.parametrize(
    "role",
    [
        "evaluator_functional",
        "evaluator_technical",
        "evaluator_economic",
        "internal_collaborator",
        "approver",
        "tenant_admin",
    ],
)
def test_fase9_role_membership_without_vendor_org_id_succeeds(role: Role) -> None:
    # Fase 9 (RBAC completo, spec §4): every one of these new roles is
    # tenant-scoped like evaluation_owner, never vendor-scoped.
    membership = Membership.create(tenant_id="t", user_id="u", role=role)
    assert membership.role == role
    assert membership.vendor_org_id is None


@pytest.mark.parametrize(
    "role",
    ["evaluator_functional", "evaluator_technical", "evaluator_economic", "tenant_admin"],
)
def test_fase9_role_membership_rejects_vendor_org_id(role: Role) -> None:
    with pytest.raises(ValueError, match="vendor_contact"):
        Membership.create(tenant_id="t", user_id="u", role=role, vendor_org_id="v")


def test_membership_round_trips_through_document() -> None:
    membership = Membership.create(tenant_id="t", user_id="u", role="evaluator_functional")
    restored = Membership.from_document(membership.to_document())
    assert restored == membership


def test_user_without_password_has_none_hash() -> None:
    user = User.create(display_name="A", email="a@example.com")
    assert user.password_hash is None
    assert user.oidc_identities == ()


def test_user_round_trips_with_password_hash() -> None:
    user = User.create(display_name="A", email="a@example.com", password_hash="argon2-hash")
    restored = User.from_document(user.to_document())
    assert restored == user
    assert restored.password_hash == "argon2-hash"


def test_user_with_oidc_identity_round_trips() -> None:
    user = User.create(display_name="A", email="a@example.com")
    identity = OidcIdentity(provider="microsoft", subject="sub-1", linked_at=datetime.now(UTC))
    linked = user.with_oidc_identity(identity)

    restored = User.from_document(linked.to_document())

    assert restored.oidc_identities == (identity,)
    assert user.oidc_identities == ()  # with_oidc_identity does not mutate the original
