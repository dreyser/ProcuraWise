from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from pymongo.errors import DuplicateKeyError

from procurawise.audit.models import AuditEvent
from procurawise.audit.repository import AuditEventRepository
from procurawise.shared.context import ActorContext

pytestmark = pytest.mark.docker

_ACTOR = ActorContext(
    membership_id="membership-1",
    user_id="user-1",
    tenant_id="audit-repo-tenant-a",
    tenant_name="Tenant A",
    role="evaluation_owner",
    vendor_org_id=None,
    display_name="Owner",
)


@pytest.fixture(autouse=True)
def _clean_audit_events(mongo_test_db):
    yield
    mongo_test_db["audit_events"].delete_many({})


def _event(**overrides) -> AuditEvent:
    defaults = dict(
        tenant_id=_ACTOR.tenant_id,
        actor=_ACTOR,
        action="evaluation_created",
        resource_type="evaluation",
        resource_id="eval-1",
        evaluation_id="eval-1",
        retention_days=365,
    )
    defaults.update(overrides)
    return AuditEvent.create(**defaults)


def test_repository_exposes_no_mutation_methods() -> None:
    """The append-only guarantee (plan §8): AuditEventRepository must never
    expose update/delete/replace - a caller can only ever `record` (insert)
    or read."""
    forbidden = {"update", "update_one", "delete", "delete_one", "replace", "replace_one"}
    exposed = {name for name in dir(AuditEventRepository) if not name.startswith("_")}
    assert exposed.isdisjoint(forbidden)
    assert exposed == {"record", "list_for_evaluation"}


def test_recording_the_same_event_twice_raises_instead_of_upserting(mongo_test_db) -> None:
    """`record` is a plain insert, never an upsert - persisting the exact
    same AuditEvent document twice must fail on the unique `_id`, not
    silently succeed a second time (which is what an upsert-based
    implementation would do)."""
    repo = AuditEventRepository(mongo_test_db)
    event = _event()
    repo.record(_ACTOR.tenant_id, event.to_document())
    with pytest.raises(DuplicateKeyError):
        repo.record(_ACTOR.tenant_id, event.to_document())
    assert mongo_test_db["audit_events"].count_documents({"_id": event.id}) == 1


def test_two_distinct_events_for_the_same_resource_both_persist(mongo_test_db) -> None:
    repo = AuditEventRepository(mongo_test_db)
    first = _event()
    second = _event()
    repo.record(_ACTOR.tenant_id, first.to_document())
    repo.record(_ACTOR.tenant_id, second.to_document())
    count = mongo_test_db["audit_events"].count_documents({"evaluation_id": "eval-1"})
    assert count == 2


def test_list_for_evaluation_is_scoped_to_tenant(mongo_test_db) -> None:
    repo = AuditEventRepository(mongo_test_db)
    own_event = _event()
    other_tenant_actor = replace(_ACTOR, tenant_id="audit-repo-tenant-b")
    other_event = _event(tenant_id="audit-repo-tenant-b", actor=other_tenant_actor)
    repo.record(_ACTOR.tenant_id, own_event.to_document())
    repo.record("audit-repo-tenant-b", other_event.to_document())

    docs = repo.list_for_evaluation(_ACTOR.tenant_id, "eval-1", limit=10, cursor=None)
    ids = {doc["_id"] for doc in docs}
    assert own_event.id in ids
    assert other_event.id not in ids


def test_list_for_evaluation_orders_newest_first_and_paginates(mongo_test_db) -> None:
    repo = AuditEventRepository(mongo_test_db)
    base = datetime.now(UTC)
    events = []
    for i in range(3):
        event = _event()
        # occurred_at is set inside AuditEvent.create; override directly via
        # to_document for deterministic ordering across the 3 seeded events.
        doc = event.to_document()
        doc["occurred_at"] = base + timedelta(seconds=i)
        doc["expires_at"] = doc["occurred_at"] + timedelta(days=365)
        repo.record(_ACTOR.tenant_id, doc)
        events.append(doc)

    first_page = repo.list_for_evaluation(_ACTOR.tenant_id, "eval-1", limit=2, cursor=None)
    assert len(first_page) == 3  # limit+1 fetched, caller (service) trims/derives next_cursor
    returned_ids_desc = [doc["_id"] for doc in first_page[:2]]
    assert returned_ids_desc == [events[2]["_id"], events[1]["_id"]]
