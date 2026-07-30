import pytest

from tests.conftest import bearer_headers_for, tenant_ids

pytestmark = pytest.mark.docker


@pytest.fixture(autouse=True)
def _clean_assignments(mongo_test_db):
    yield
    mongo_test_db["assignments"].delete_many({})


def _create_evaluation_with_functional_requirement(client, owner_headers) -> tuple[str, str]:
    created = client.post(
        "/api/v1/evaluations",
        json={"name": "Aislamiento de assignments", "description": ""},
        headers=owner_headers,
    )
    evaluation_id = created.json()["id"]
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "functional",
            "category": "Seccion Beta",
            "title": "T",
            "description": "D",
            "priority": "important",
            "response_type": "compliant_status",
            "weight": 10.0,
            "required": True,
            "display_order": 1,
        },
        headers=owner_headers,
    )
    return evaluation_id, "Seccion Beta"


def test_owner_of_other_tenant_gets_404_listing_assignments(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id, _section = _create_evaluation_with_functional_requirement(
        client, owner_a_headers
    )

    response = client.get(
        f"/api/v1/evaluations/{evaluation_id}/assignments", headers=owner_b_headers
    )

    assert response.status_code == 404


def test_cannot_assign_an_evaluator_membership_from_another_tenant(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id, section = _create_evaluation_with_functional_requirement(client, owner_a_headers)
    # A membership_id that is real, but belongs to tenant_b, must never be
    # assignable into a tenant_a evaluation - the service resolves the
    # membership tenant-scoped (find_by_id_and_tenant), not by find_by_id.
    # evaluator_technical is the sub-role dev_seed.py seeds for tenant_b; the
    # cross-tenant check must reject it before any role/dimension match is
    # even considered.
    tenant_b_evaluator_membership_id = seeded_actors[(tenant_b, "evaluator_technical")]

    response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/assignments",
        json={
            "dimension": "functional",
            "section": section,
            "evaluator_membership_id": tenant_b_evaluator_membership_id,
        },
        headers=owner_a_headers,
    )

    assert response.status_code == 400
