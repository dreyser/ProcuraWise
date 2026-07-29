import pytest

from procurawise.identity.dev_provider import DEV_ACTOR_HEADER
from tests.conftest import tenant_ids

pytestmark = pytest.mark.docker


def _create_evaluation(client, owner_headers) -> str:
    created = client.post(
        "/api/v1/evaluations",
        json={"name": "RFP con choice", "description": ""},
        headers=owner_headers,
    )
    assert created.status_code == 201
    return created.json()["id"]


def _create_single_choice_requirement(client, owner_headers, evaluation_id: str) -> str:
    created = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "functional",
            "category": "Core",
            "title": "Modelo de despliegue",
            "description": "Como se despliega la solucion",
            "priority": "important",
            "response_type": "single_choice",
            "weight": 40.0,
            "required": True,
            "display_order": 1,
            "options": ["SaaS", "On-premise"],
        },
        headers=owner_headers,
    )
    assert created.status_code == 201
    return created.json()["id"]


def _create_plain_requirement(client, owner_headers, evaluation_id: str) -> str:
    created = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "functional",
            "category": "Core",
            "title": "Descripcion general",
            "description": "Descripcion libre de la solucion",
            "priority": "important",
            "response_type": "text",
            "weight": 40.0,
            "required": True,
            "display_order": 1,
        },
        headers=owner_headers,
    )
    assert created.status_code == 201
    return created.json()["id"]


def test_patch_to_single_choice_without_options_is_rejected(client, seeded_actors) -> None:
    tenant_a, _tenant_b = tenant_ids(seeded_actors)
    owner_headers = {DEV_ACTOR_HEADER: seeded_actors[(tenant_a, "evaluation_owner")]}
    evaluation_id = _create_evaluation(client, owner_headers)
    requirement_id = _create_plain_requirement(client, owner_headers, evaluation_id)

    response = client.patch(
        f"/api/v1/evaluations/{evaluation_id}/requirements/{requirement_id}",
        json={"response_type": "single_choice"},
        headers=owner_headers,
    )

    assert response.status_code == 400

    unchanged = client.get(f"/api/v1/evaluations/{evaluation_id}", headers=owner_headers)
    requirement = next(r for r in unchanged.json()["requirements"] if r["id"] == requirement_id)
    assert requirement["response_type"] == "text"


def test_patch_clearing_options_on_existing_choice_is_rejected(client, seeded_actors) -> None:
    tenant_a, _tenant_b = tenant_ids(seeded_actors)
    owner_headers = {DEV_ACTOR_HEADER: seeded_actors[(tenant_a, "evaluation_owner")]}
    evaluation_id = _create_evaluation(client, owner_headers)
    requirement_id = _create_single_choice_requirement(client, owner_headers, evaluation_id)

    response = client.patch(
        f"/api/v1/evaluations/{evaluation_id}/requirements/{requirement_id}",
        json={"options": []},
        headers=owner_headers,
    )

    assert response.status_code == 400

    unchanged = client.get(f"/api/v1/evaluations/{evaluation_id}", headers=owner_headers)
    requirement = next(r for r in unchanged.json()["requirements"] if r["id"] == requirement_id)
    assert requirement["options"] == ["SaaS", "On-premise"]


def test_patch_from_choice_to_another_type_is_allowed(client, seeded_actors) -> None:
    tenant_a, _tenant_b = tenant_ids(seeded_actors)
    owner_headers = {DEV_ACTOR_HEADER: seeded_actors[(tenant_a, "evaluation_owner")]}
    evaluation_id = _create_evaluation(client, owner_headers)
    requirement_id = _create_single_choice_requirement(client, owner_headers, evaluation_id)

    response = client.patch(
        f"/api/v1/evaluations/{evaluation_id}/requirements/{requirement_id}",
        json={"response_type": "text"},
        headers=owner_headers,
    )

    assert response.status_code == 200
    assert response.json()["response_type"] == "text"


def test_partial_patch_preserving_valid_combination_succeeds(client, seeded_actors) -> None:
    tenant_a, _tenant_b = tenant_ids(seeded_actors)
    owner_headers = {DEV_ACTOR_HEADER: seeded_actors[(tenant_a, "evaluation_owner")]}
    evaluation_id = _create_evaluation(client, owner_headers)
    requirement_id = _create_single_choice_requirement(client, owner_headers, evaluation_id)

    response = client.patch(
        f"/api/v1/evaluations/{evaluation_id}/requirements/{requirement_id}",
        json={"title": "Modelo de despliegue preferido"},
        headers=owner_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Modelo de despliegue preferido"
    assert body["response_type"] == "single_choice"
    assert body["options"] == ["SaaS", "On-premise"]


def test_cross_tenant_patch_returns_404(client, seeded_actors) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = {DEV_ACTOR_HEADER: seeded_actors[(tenant_a, "evaluation_owner")]}
    owner_b_headers = {DEV_ACTOR_HEADER: seeded_actors[(tenant_b, "evaluation_owner")]}
    evaluation_id = _create_evaluation(client, owner_a_headers)
    requirement_id = _create_plain_requirement(client, owner_a_headers, evaluation_id)

    response = client.patch(
        f"/api/v1/evaluations/{evaluation_id}/requirements/{requirement_id}",
        json={"title": "Intento cross-tenant"},
        headers=owner_b_headers,
    )

    assert response.status_code == 404
