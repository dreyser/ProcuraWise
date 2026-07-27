import pytest

from procurawise.identity.models import Membership


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


def test_membership_round_trips_through_document() -> None:
    membership = Membership.create(tenant_id="t", user_id="u", role="evaluator")
    restored = Membership.from_document(membership.to_document())
    assert restored == membership
