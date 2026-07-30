from datetime import timedelta

from procurawise.audit.models import AuditEvent
from procurawise.shared.context import ActorContext

_BUYER = ActorContext(
    membership_id="membership-1",
    user_id="user-1",
    tenant_id="tenant-1",
    tenant_name="Tenant One",
    role="evaluation_owner",
    vendor_org_id=None,
    display_name="Owner One",
)

_VENDOR = ActorContext(
    membership_id="membership-2",
    user_id="user-2",
    tenant_id="tenant-1",
    tenant_name="Tenant One",
    role="vendor_contact",
    vendor_org_id="vendor-org-1",
    display_name="Vendor One",
)


def test_create_derives_buyer_actor_type_from_buyer_role() -> None:
    event = AuditEvent.create(
        tenant_id="tenant-1",
        actor=_BUYER,
        action="evaluation_created",
        resource_type="evaluation",
        resource_id="eval-1",
        retention_days=365,
    )
    assert event.actor_type == "buyer"
    assert event.actor_role == "evaluation_owner"
    assert event.actor_membership_id == "membership-1"
    assert event.actor_vendor_org_id is None


def test_create_derives_vendor_contact_actor_type() -> None:
    event = AuditEvent.create(
        tenant_id="tenant-1",
        actor=_VENDOR,
        action="proposal_submitted",
        resource_type="proposal",
        resource_id="proposal-1",
        retention_days=365,
    )
    assert event.actor_type == "vendor_contact"
    assert event.actor_vendor_org_id == "vendor-org-1"


def test_create_sets_expires_at_from_retention_days() -> None:
    event = AuditEvent.create(
        tenant_id="tenant-1",
        actor=_BUYER,
        action="evaluation_created",
        resource_type="evaluation",
        resource_id="eval-1",
        retention_days=365,
    )
    assert event.expires_at - event.occurred_at == timedelta(days=365)


def test_create_defaults_metadata_to_empty_dict() -> None:
    event = AuditEvent.create(
        tenant_id="tenant-1",
        actor=_BUYER,
        action="evaluation_created",
        resource_type="evaluation",
        resource_id="eval-1",
        retention_days=365,
    )
    assert event.metadata == {}
    assert event.outcome == "success"


def test_to_document_and_from_document_round_trip() -> None:
    event = AuditEvent.create(
        tenant_id="tenant-1",
        actor=_BUYER,
        action="requirement_updated",
        resource_type="requirement",
        resource_id="req-1",
        evaluation_id="eval-1",
        correlation_id="corr-1",
        metadata={"fields_changed": ["title"]},
        retention_days=365,
    )
    restored = AuditEvent.from_document(event.to_document())
    assert restored == event


def test_to_document_never_contains_a_raw_value_field() -> None:
    """Guards against a future change accidentally passing a whole
    before/after value through metadata (plan §10) - only structured,
    explicitly allowlisted keys belong in metadata, never "value"/"answer"/
    "comment" catch-alls."""
    event = AuditEvent.create(
        tenant_id="tenant-1",
        actor=_BUYER,
        action="requirement_updated",
        resource_type="requirement",
        resource_id="req-1",
        metadata={"fields_changed": ["weight"]},
        retention_days=365,
    )
    doc = event.to_document()
    assert set(doc["metadata"].keys()) == {"fields_changed"}
