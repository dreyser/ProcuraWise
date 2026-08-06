"""Fase 23 (backlog.md fila 23: "import Excel/CSV con preview+mapeo") -
exercises the full requirements-import flow against the real API: preview
returns parsed rows + a suggested mapping without persisting anything,
confirm creates real Requirements via the same
EvaluationRepository.add_requirements_bulk manual entry and KnowledgeTemplate
apply already use, restricted to draft evaluations."""

import pytest

from tests.conftest import bearer_headers_for, unique_actor_by_role

pytestmark = pytest.mark.docker


def _csv_upload(filename: str = "requerimientos.csv"):
    content = (
        b"Dimension,Categoria,Titulo,Descripcion,Prioridad,Peso,Obligatorio\n"
        b"functional,Core,Requerimiento importado,Descripcion,important,40,false\n"
    )
    return {"file": (filename, content, "text/csv")}


def test_preview_does_not_persist_anything(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Import RFP", "description": ""},
        headers=owner_headers,
    ).json()["id"]

    preview = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements/import/preview",
        files=_csv_upload(),
        headers=owner_headers,
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["columns"] == [
        "Dimension",
        "Categoria",
        "Titulo",
        "Descripcion",
        "Prioridad",
        "Peso",
        "Obligatorio",
    ]
    assert body["suggested_mapping"]["title"] == "Titulo"
    assert len(body["rows"]) == 1

    evaluation = client.get(f"/api/v1/evaluations/{evaluation_id}", headers=owner_headers).json()
    assert evaluation["requirements"] == []


def test_confirm_creates_real_requirements(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Import RFP 2", "description": ""},
        headers=owner_headers,
    ).json()["id"]

    confirm = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements/import/confirm",
        json={
            "requirements": [
                {
                    "dimension": "functional",
                    "category": "Core",
                    "title": "Requerimiento importado",
                    "description": "Descripcion",
                    "priority": "important",
                    "response_type": "text",
                    "weight": 40.0,
                    "required": False,
                    "display_order": 1,
                }
            ]
        },
        headers=owner_headers,
    )
    assert confirm.status_code == 201, confirm.text
    assert len(confirm.json()["requirements"]) == 1
    assert confirm.json()["requirements"][0]["title"] == "Requerimiento importado"

    evaluation = client.get(f"/api/v1/evaluations/{evaluation_id}", headers=owner_headers).json()
    assert len(evaluation["requirements"]) == 1
    assert evaluation["requirements"][0]["title"] == "Requerimiento importado"


def test_import_is_blocked_outside_draft(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    from procurawise.identity.dev_provider import DEV_ACTOR_HEADER
    from tests.conftest import approve_and_publish

    vendor_org_id = client.get(
        "/api/v1/me", headers={DEV_ACTOR_HEADER: vendor_membership_id}
    ).json()["vendor_org_id"]

    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Import blocked RFP", "description": ""},
        headers=owner_headers,
    ).json()["id"]
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "functional",
            "category": "Core",
            "title": "Req 1",
            "description": "d",
            "priority": "important",
            "response_type": "text",
            "weight": 40.0,
            "required": False,
            "display_order": 1,
        },
        headers=owner_headers,
    )
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "technical",
            "category": "Core",
            "title": "Req 2",
            "description": "d",
            "priority": "important",
            "response_type": "text",
            "weight": 20.0,
            "required": False,
            "display_order": 2,
        },
        headers=owner_headers,
    )
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/vendors",
        json={"vendor_org_id": vendor_org_id},
        headers=owner_headers,
    )
    approver_membership_id = seeded_actors[(tenant_a, "approver")]
    approver_headers = bearer_headers_for(approver_membership_id, mongo_test_settings)
    approve_and_publish(
        client, owner_headers, approver_membership_id, approver_headers, evaluation_id
    )

    preview = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements/import/preview",
        files=_csv_upload(),
        headers=owner_headers,
    )
    assert preview.status_code == 409


def test_non_owner_cannot_confirm_import(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, evaluator_membership_id = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluator_headers = bearer_headers_for(evaluator_membership_id, mongo_test_settings)
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Import RBAC RFP", "description": ""},
        headers=owner_headers,
    ).json()["id"]

    confirm = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements/import/confirm",
        json={"requirements": []},
        headers=evaluator_headers,
    )
    assert confirm.status_code == 403
