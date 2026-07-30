import pytest

from procurawise.audit.models import AuditEvent
from procurawise.audit.repository import AuditEventRepository
from procurawise.identity.dev_provider import DEV_ACTOR_HEADER
from procurawise.shared.context import ActorContext
from tests.conftest import bearer_headers_for, tenant_ids, unique_actor_by_role

pytestmark = pytest.mark.docker


@pytest.fixture(autouse=True)
def _clean_audit_events(mongo_test_db):
    yield
    mongo_test_db["audit_events"].delete_many({})


def _create_evaluation(client, owner_headers) -> str:
    response = client.post(
        "/api/v1/evaluations",
        json={"name": "Audit Isolation RFP", "description": ""},
        headers=owner_headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


def _seed_audit_event(mongo_test_db, tenant_id: str, evaluation_id: str, membership_id: str) -> str:
    actor = ActorContext(
        membership_id=membership_id,
        user_id="user-x",
        tenant_id=tenant_id,
        tenant_name="Tenant",
        role="evaluation_owner",
        vendor_org_id=None,
        display_name="Owner",
    )
    event = AuditEvent.create(
        tenant_id=tenant_id,
        actor=actor,
        action="evaluation_created",
        resource_type="evaluation",
        resource_id=evaluation_id,
        evaluation_id=evaluation_id,
        retention_days=365,
    )
    AuditEventRepository(mongo_test_db).record(tenant_id, event.to_document())
    return event.id


def test_owner_can_list_audit_events_for_own_evaluation(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    tenant_a, _tenant_b = tenant_ids(seeded_actors)
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    # _create_evaluation itself already emits a real `evaluation_created`
    # AuditEvent (Bloque 3 instrumentation) - the manually seeded event below
    # is an *additional* one, so a correct response contains both.
    evaluation_id = _create_evaluation(client, owner_headers)
    event_id = _seed_audit_event(
        mongo_test_db, tenant_a, evaluation_id, seeded_actors[(tenant_a, "evaluation_owner")]
    )

    response = client.get(
        f"/api/v1/evaluations/{evaluation_id}/audit-events", headers=owner_headers
    )

    assert response.status_code == 200
    body = response.json()
    returned_ids = {item["id"] for item in body["items"]}
    assert event_id in returned_ids
    assert len(body["items"]) == 2
    actions = {item["action"] for item in body["items"]}
    assert actions == {"evaluation_created"}


def test_evaluator_of_other_tenant_gets_404_for_evaluation(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = _create_evaluation(client, owner_a_headers)

    response = client.get(
        f"/api/v1/evaluations/{evaluation_id}/audit-events", headers=owner_b_headers
    )

    assert response.status_code == 404


def test_seeded_audit_event_for_tenant_a_is_invisible_from_tenant_b_query(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    """Even if a tenant-B owner somehow queried the same evaluation_id (e.g.
    a UUID collision, or a bug in the 404 check above), the repository layer
    itself must never return tenant A's AuditEvent to tenant B - the 404
    above is a defense-in-depth belt, TenantCollection is the actual
    isolation mechanism (plan §6/§12)."""
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = _create_evaluation(client, owner_a_headers)
    _seed_audit_event(
        mongo_test_db, tenant_a, evaluation_id, seeded_actors[(tenant_a, "evaluation_owner")]
    )

    docs_from_tenant_b_scope = AuditEventRepository(mongo_test_db).list_for_evaluation(
        tenant_b, evaluation_id, limit=10, cursor=None
    )
    assert docs_from_tenant_b_scope == []


def test_vendor_contact_without_buyer_credentials_gets_401(client, seeded_actors) -> None:
    """vendor_contact stays on the interim dev-header mechanism (AUTH-PROD
    scope decision #1), which this buyer-only route does not accept - no
    Authorization bearer means authentication itself fails before any role
    check runs (401, not 403 - same strengthened-isolation pattern AUTH-PROD
    already established for other buyer routes)."""
    _vendor_tenant_id, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")

    response = client.get(
        "/api/v1/evaluations/some-evaluation-id/audit-events",
        headers={DEV_ACTOR_HEADER: vendor_membership_id},
    )

    assert response.status_code == 401
