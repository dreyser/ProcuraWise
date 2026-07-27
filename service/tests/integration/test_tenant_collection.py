import pytest

from procurawise.shared.tenant_collection import TenantCollection, TenantScopeError

pytestmark = pytest.mark.docker

PROBE_COLLECTION_NAME = "_tenant_collection_probe"


@pytest.fixture
def probe_collection(mongo_test_db):
    collection = mongo_test_db[PROBE_COLLECTION_NAME]
    yield collection
    collection.drop()


@pytest.fixture
def scoped_to_tenant_a(probe_collection):
    return TenantCollection(probe_collection, "tenant-a")


def test_insert_forces_resolved_tenant_id(scoped_to_tenant_a):
    scoped_to_tenant_a.insert_one({"_id": "doc-1", "name": "x"})
    doc = scoped_to_tenant_a.find_one({"_id": "doc-1"})
    assert doc is not None
    assert doc["tenant_id"] == "tenant-a"


def test_insert_rejects_mismatched_tenant_id(scoped_to_tenant_a):
    with pytest.raises(TenantScopeError):
        scoped_to_tenant_a.insert_one({"_id": "doc-2", "tenant_id": "tenant-b"})


def test_find_one_cannot_see_another_tenants_document(scoped_to_tenant_a, probe_collection):
    probe_collection.insert_one({"_id": "doc-3", "tenant_id": "tenant-b"})
    assert scoped_to_tenant_a.find_one({"_id": "doc-3"}) is None


def test_find_one_rejects_filter_tenant_id_collision(scoped_to_tenant_a):
    with pytest.raises(TenantScopeError):
        scoped_to_tenant_a.find_one({"tenant_id": "tenant-b"})


def test_update_one_with_set_operator_applies_normally(scoped_to_tenant_a):
    scoped_to_tenant_a.insert_one({"_id": "doc-4", "name": "before"})
    scoped_to_tenant_a.update_one({"_id": "doc-4"}, {"$set": {"name": "after"}})
    doc = scoped_to_tenant_a.find_one({"_id": "doc-4"})
    assert doc is not None
    assert doc["name"] == "after"
    assert doc["tenant_id"] == "tenant-a"


def test_update_one_rejects_set_tenant_id(scoped_to_tenant_a):
    scoped_to_tenant_a.insert_one({"_id": "doc-5"})
    with pytest.raises(TenantScopeError):
        scoped_to_tenant_a.update_one({"_id": "doc-5"}, {"$set": {"tenant_id": "tenant-b"}})


def test_update_one_rejects_unset_tenant_id(scoped_to_tenant_a):
    scoped_to_tenant_a.insert_one({"_id": "doc-6"})
    with pytest.raises(TenantScopeError):
        scoped_to_tenant_a.update_one({"_id": "doc-6"}, {"$unset": {"tenant_id": ""}})


def test_update_one_rejects_mixed_operator_and_plain_keys(scoped_to_tenant_a):
    scoped_to_tenant_a.insert_one({"_id": "doc-7", "name": "before"})
    with pytest.raises(TenantScopeError):
        scoped_to_tenant_a.update_one({"_id": "doc-7"}, {"$set": {"name": "after"}, "extra": "y"})
    # Rejected before touching the database - the document is untouched.
    doc = scoped_to_tenant_a.find_one({"_id": "doc-7"})
    assert doc is not None
    assert doc["name"] == "before"


def test_update_one_replacement_rejects_mismatched_tenant_id(scoped_to_tenant_a):
    scoped_to_tenant_a.insert_one({"_id": "doc-8"})
    with pytest.raises(TenantScopeError):
        scoped_to_tenant_a.update_one({"_id": "doc-8"}, {"tenant_id": "tenant-b", "name": "y"})


def test_update_one_replacement_forces_resolved_tenant_id(scoped_to_tenant_a):
    scoped_to_tenant_a.insert_one({"_id": "doc-9"})
    scoped_to_tenant_a.update_one({"_id": "doc-9"}, {"name": "z"})
    doc = scoped_to_tenant_a.find_one({"_id": "doc-9"})
    assert doc is not None
    assert doc["tenant_id"] == "tenant-a"
    assert doc["name"] == "z"


def test_update_one_replacement_accepts_matching_tenant_id(scoped_to_tenant_a):
    scoped_to_tenant_a.insert_one({"_id": "doc-10"})
    scoped_to_tenant_a.update_one({"_id": "doc-10"}, {"tenant_id": "tenant-a", "name": "w"})
    doc = scoped_to_tenant_a.find_one({"_id": "doc-10"})
    assert doc is not None
    assert doc["tenant_id"] == "tenant-a"
    assert doc["name"] == "w"


def test_update_one_replacement_does_not_mutate_caller_document(scoped_to_tenant_a):
    scoped_to_tenant_a.insert_one({"_id": "doc-11"})
    replacement = {"name": "original-dict"}

    scoped_to_tenant_a.update_one({"_id": "doc-11"}, replacement)

    assert replacement == {"name": "original-dict"}
    assert "tenant_id" not in replacement


def test_update_one_rejects_filter_tenant_id_collision(scoped_to_tenant_a):
    with pytest.raises(TenantScopeError):
        scoped_to_tenant_a.update_one({"tenant_id": "tenant-b"}, {"$set": {"name": "x"}})


def test_update_one_operator_cannot_reach_another_tenants_document(
    scoped_to_tenant_a, probe_collection
):
    probe_collection.insert_one({"_id": "doc-12", "tenant_id": "tenant-b", "name": "untouched"})
    result = scoped_to_tenant_a.update_one({"_id": "doc-12"}, {"$set": {"name": "hijacked"}})
    assert result.matched_count == 0
    doc = probe_collection.find_one({"_id": "doc-12"})
    assert doc is not None
    assert doc["name"] == "untouched"


def test_update_one_replacement_cannot_reach_another_tenants_document(
    scoped_to_tenant_a, probe_collection
):
    probe_collection.insert_one({"_id": "doc-13", "tenant_id": "tenant-b", "name": "untouched"})
    result = scoped_to_tenant_a.update_one({"_id": "doc-13"}, {"name": "hijacked"})
    assert result.matched_count == 0
    doc = probe_collection.find_one({"_id": "doc-13"})
    assert doc is not None
    assert doc["name"] == "untouched"


def test_update_one_upsert_with_operator_stays_in_resolved_tenant(scoped_to_tenant_a):
    result = scoped_to_tenant_a.update_one(
        {"_id": "doc-14"}, {"$set": {"name": "created"}}, upsert=True
    )
    assert result.upserted_id == "doc-14"
    doc = scoped_to_tenant_a.find_one({"_id": "doc-14"})
    assert doc is not None
    assert doc["tenant_id"] == "tenant-a"
    assert doc["name"] == "created"


def test_update_one_upsert_replacement_stays_in_resolved_tenant(scoped_to_tenant_a):
    result = scoped_to_tenant_a.update_one({"_id": "doc-15"}, {"name": "created"}, upsert=True)
    assert result.upserted_id == "doc-15"
    doc = scoped_to_tenant_a.find_one({"_id": "doc-15"})
    assert doc is not None
    assert doc["tenant_id"] == "tenant-a"
    assert doc["name"] == "created"


def test_delete_one_cannot_reach_another_tenants_document(scoped_to_tenant_a, probe_collection):
    probe_collection.insert_one({"_id": "doc-16", "tenant_id": "tenant-b"})
    scoped_to_tenant_a.delete_one({"_id": "doc-16"})
    assert probe_collection.find_one({"_id": "doc-16"}) is not None


def test_count_documents_is_tenant_scoped(scoped_to_tenant_a, probe_collection):
    probe_collection.insert_one({"_id": "doc-17", "tenant_id": "tenant-b"})
    scoped_to_tenant_a.insert_one({"_id": "doc-18"})
    assert scoped_to_tenant_a.count_documents({}) == 1
