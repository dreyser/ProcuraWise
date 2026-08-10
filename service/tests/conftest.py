import pytest
from fastapi.testclient import TestClient

from procurawise.api.main import app
from procurawise.dev_seed import SEEDED_COLLECTIONS, seed
from procurawise.identity.jwt_provider import create_access_token, create_vendor_access_token
from procurawise.identity.repository import MembershipRepository, TenantRepository, UserRepository
from procurawise.identity.service import IdentityService
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.mongo import get_database, get_mongo_client
from procurawise.shared.rate_limit import reset_rate_limits
from procurawise.shared.storage import AzureBlobStorage

TEST_MONGO_DB_NAME = "procurawise_test"
TEST_STORAGE_CONTAINER_NAME = "procurawise-test"
TEST_DOCUMENTS_CONTAINER_NAME = "procurawise-test-documents"


@pytest.fixture
def mongo_test_settings() -> Settings:
    return Settings(_env_file=None, mongodb_db_name=TEST_MONGO_DB_NAME)


@pytest.fixture
def mongo_test_db(mongo_test_settings: Settings):
    client = get_mongo_client(mongo_test_settings)
    db = client[mongo_test_settings.mongodb_db_name]
    yield db
    db.drop_collection("_infra_probe")


@pytest.fixture
def seeded_actors(mongo_test_settings: Settings, mongo_test_db):
    """Membership id keyed by (tenant_id, role) - shared across every
    docker-marked test that needs a seeded identity fixture plus (as of
    VS-2B) one seeded draft Evaluation+Proposal under tenant_a (see
    dev_seed.py). Keeps the *first* Membership per key, not the last
    (`setdefault`, not a dict comprehension) - Fase 15 added a second
    vendor_contact Membership on the same (tenant_id, "vendor_contact") key
    (a second collaborator on the same vendor org, seeded right after the
    first), and every existing test resolving "the" vendor actor via
    `unique_actor_by_role` must keep landing on the first one. Tests that
    need the second collaborator specifically use
    `second_vendor_collaborator_membership_id` below instead."""
    memberships = seed(mongo_test_settings)
    by_key: dict[tuple[str, str], str] = {}
    for m in memberships:
        by_key.setdefault((m.tenant_id, m.role), m.id)
    yield by_key
    for name in SEEDED_COLLECTIONS:
        mongo_test_db[name].drop()


@pytest.fixture
def client(mongo_test_settings: Settings, seeded_actors):
    # Fase 26 (Hardening): the rate limiter (shared/rate_limit.py) is a
    # process-wide singleton, not per-app/per-test - without this reset, hit
    # counts would leak between unrelated test functions sharing this
    # pytest session (e.g. this file alone drives /auth/login well past
    # rate_limit_login_max_attempts across its own tests).
    reset_rate_limits()
    app.dependency_overrides[get_settings] = lambda: mongo_test_settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def tenant_ids(seeded_actors: dict[tuple[str, str], str]) -> tuple[str, str]:
    """Returns two arbitrary, distinct tenant ids from the seed. The labels
    "tenant_a"/"tenant_b" only mean "some tenant" / "some other tenant" -
    tenant/membership ids are random UUIDs, so this sorted order carries no
    semantic meaning. Only use where a test needs two distinct tenants but
    doesn't care which one is which."""
    tenants = {tenant_id for tenant_id, _role in seeded_actors}
    tenant_a, tenant_b = sorted(tenants)
    return tenant_a, tenant_b


def bearer_headers_for(membership_id: str, mongo_test_settings: Settings) -> dict[str, str]:
    """Mints a real access token for a seeded buyer Membership, in-process
    (no HTTP round trip through /auth/login + /auth/switch-tenant) - existing
    business-logic tests only need "a valid token for actor X", not to
    exercise the login flow itself (see tests/api/test_auth_router.py for
    that). AUTH-PROD replaced the dev-header mechanism for every route that
    goes through shared.context.require_role (evaluations/proposals/scoring/
    vendor-organizations)."""
    db = get_database(mongo_test_settings)
    identity_service = IdentityService(
        tenants=TenantRepository(db), users=UserRepository(db), memberships=MembershipRepository(db)
    )
    context = identity_service.resolve_actor_context(membership_id)
    token, _ = create_access_token(context, mongo_test_settings)
    return {"Authorization": f"Bearer {token}"}


def vendor_bearer_headers_for(membership_id: str, mongo_test_settings: Settings) -> dict[str, str]:
    """Fase 15: the vendor-side mirror of bearer_headers_for above - mints a
    real vendor access token (token_use=vendor_access), in-process, for a
    seeded vendor_contact Membership. vendor_portal now requires this same
    real-JWT mechanism buyer routes have required since AUTH-PROD; the
    interim DEV_ACTOR_HEADER mechanism is no longer accepted there (still
    used only for /dev/actors and /me, unchanged)."""
    db = get_database(mongo_test_settings)
    identity_service = IdentityService(
        tenants=TenantRepository(db), users=UserRepository(db), memberships=MembershipRepository(db)
    )
    context = identity_service.resolve_actor_context(membership_id)
    token, _ = create_vendor_access_token(context, mongo_test_settings)
    return {"Authorization": f"Bearer {token}"}


def second_vendor_collaborator_membership_id(mongo_test_db, tenant_id: str) -> str:
    """Fase 15: dev_seed.py seeds a second vendor_contact Membership
    (vendor.a2@dev.procurawise.local) on the same vendor_org_id as the
    primary seeded vendor actor, deliberately kept out of the
    `seeded_actors` fixture (see dev_seed.py's comment - two Membership rows
    sharing the same (tenant_id, "vendor_contact") key would silently
    collide there). Tests that need "the other collaborator on the same
    org" resolve it here instead."""
    user_doc = mongo_test_db["users"].find_one({"email": "vendor.a2@dev.procurawise.local"})
    membership_doc = mongo_test_db["memberships"].find_one(
        {"tenant_id": tenant_id, "user_id": user_doc["_id"], "role": "vendor_contact"}
    )
    return str(membership_doc["_id"])


def approve_and_publish(
    client,
    owner_headers: dict[str, str],
    approver_membership_id: str,
    approver_headers: dict[str, str],
    evaluation_id: str,
    *,
    response_deadline: str = "2030-01-01T00:00:00Z",
) -> None:
    """Fase 12 precursor every start-collection call now requires: set a
    response_deadline + approver, request approval, have the assigned
    approver approve, then publish. Every pre-Fase-12 test that reaches
    collecting_responses by calling start-collection directly must run this
    first - see plan §22/§32 Blocker 1-3."""
    deadline_response = client.patch(
        f"/api/v1/evaluations/{evaluation_id}",
        json={"response_deadline": response_deadline},
        headers=owner_headers,
    )
    assert deadline_response.status_code == 200, deadline_response.text

    approver_response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/approver",
        json={"approver_membership_id": approver_membership_id},
        headers=owner_headers,
    )
    assert approver_response.status_code == 200, approver_response.text

    request_response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/request-approval",
        headers=owner_headers,
    )
    assert request_response.status_code == 200, request_response.text

    approve_response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/approve",
        json={},
        headers=approver_headers,
    )
    assert approve_response.status_code == 200, approve_response.text

    publish_response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/start-collection", headers=owner_headers
    )
    assert publish_response.status_code == 200, publish_response.text


def unique_actor_by_role(seeded_actors: dict[tuple[str, str], str], role: str) -> tuple[str, str]:
    """Resolves (tenant_id, membership_id) for the seeded actor with this
    role, asserting there is exactly one."""
    matches = [
        (tenant_id, membership_id)
        for (tenant_id, actor_role), membership_id in seeded_actors.items()
        if actor_role == role
    ]
    assert len(matches) == 1, (
        f"expected exactly one seeded actor with role={role!r}, found {len(matches)}: {matches}"
    )
    return matches[0]


@pytest.fixture
def blob_test_settings() -> Settings:
    return Settings(_env_file=None, storage_container_name=TEST_STORAGE_CONTAINER_NAME)


@pytest.fixture
def blob_test_storage(blob_test_settings: Settings):
    storage = AzureBlobStorage.from_settings(blob_test_settings)
    storage.ensure_container()
    yield storage


@pytest.fixture
def documents_test_settings() -> Settings:
    return Settings(
        _env_file=None,
        mongodb_db_name=TEST_MONGO_DB_NAME,
        documents_container_name=TEST_DOCUMENTS_CONTAINER_NAME,
    )


@pytest.fixture
def documents_test_storage(documents_test_settings: Settings):
    storage = AzureBlobStorage.from_settings(
        documents_test_settings, container_name=documents_test_settings.documents_container_name
    )
    storage.ensure_container()
    yield storage
