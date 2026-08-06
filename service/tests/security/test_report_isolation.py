"""CLAUDE.md S4: every new route touching business data requires its own
negative tenant-isolation test. Covers cross-tenant 404s (never revealing
that an Evaluation/Report exists in another tenant), role-based 403s
(vendor_contact and non-owner buyer roles) for both the reports/* endpoints
and the requirements/import/* endpoints introduced in Fase 23."""

import pytest

from tests.conftest import bearer_headers_for, tenant_ids, unique_actor_by_role

pytestmark = pytest.mark.docker


def _csv_upload() -> dict:
    content = (
        b"Dimension,Categoria,Titulo,Descripcion,Prioridad,Peso,Obligatorio\n"
        b"functional,Core,Req importado,Descripcion,important,40,false\n"
    )
    return {"file": ("r.csv", content, "text/csv")}


def _create_evaluation(client, owner_headers: dict, name: str) -> str:
    return client.post(
        "/api/v1/evaluations", json={"name": name, "description": ""}, headers=owner_headers
    ).json()["id"]


# --- reports/* ---------------------------------------------------------


def test_list_reports_for_other_tenants_evaluation_returns_404(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = _create_evaluation(client, owner_a_headers, "Tenant A reports RFP")

    response = client.get(f"/api/v1/evaluations/{evaluation_id}/reports", headers=owner_b_headers)
    assert response.status_code == 404


def test_readiness_for_other_tenants_evaluation_returns_404(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = _create_evaluation(client, owner_a_headers, "Tenant A readiness RFP")

    response = client.get(
        f"/api/v1/evaluations/{evaluation_id}/reports/readiness",
        params={"report_type": "qna_summary"},
        headers=owner_b_headers,
    )
    assert response.status_code == 404


def test_create_report_for_other_tenants_evaluation_returns_404(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = _create_evaluation(client, owner_a_headers, "Tenant A create RFP")

    response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/reports",
        json={"report_type": "qna_summary", "format": "pdf"},
        headers=owner_b_headers,
    )
    assert response.status_code == 404


def test_get_report_and_download_url_never_cross_tenant(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = _create_evaluation(client, owner_a_headers, "Tenant A report detail RFP")
    report = client.post(
        f"/api/v1/evaluations/{evaluation_id}/reports",
        json={"report_type": "qna_summary", "format": "pdf"},
        headers=owner_a_headers,
    )
    assert report.status_code == 201, report.text
    report_id = report.json()["id"]

    get_attempt = client.get(
        f"/api/v1/evaluations/{evaluation_id}/reports/{report_id}", headers=owner_b_headers
    )
    assert get_attempt.status_code == 404

    download_attempt = client.get(
        f"/api/v1/evaluations/{evaluation_id}/reports/{report_id}/download-url",
        headers=owner_b_headers,
    )
    assert download_attempt.status_code == 404


def test_vendor_contact_cannot_read_report_endpoints(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    vendor_headers = bearer_headers_for(vendor_membership_id, mongo_test_settings)
    evaluation_id = _create_evaluation(client, owner_headers, "Vendor-blocked reports RFP")

    list_attempt = client.get(
        f"/api/v1/evaluations/{evaluation_id}/reports", headers=vendor_headers
    )
    assert list_attempt.status_code == 403

    readiness_attempt = client.get(
        f"/api/v1/evaluations/{evaluation_id}/reports/readiness",
        params={"report_type": "qna_summary"},
        headers=vendor_headers,
    )
    assert readiness_attempt.status_code == 403


def test_non_owner_buyer_role_cannot_generate_but_can_list(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, evaluator_membership_id = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluator_headers = bearer_headers_for(evaluator_membership_id, mongo_test_settings)
    evaluation_id = _create_evaluation(client, owner_headers, "Evaluator reports RFP")

    list_response = client.get(
        f"/api/v1/evaluations/{evaluation_id}/reports", headers=evaluator_headers
    )
    assert list_response.status_code == 200

    create_attempt = client.post(
        f"/api/v1/evaluations/{evaluation_id}/reports",
        json={"report_type": "qna_summary", "format": "pdf"},
        headers=evaluator_headers,
    )
    assert create_attempt.status_code == 403


# --- requirements/import/* ----------------------------------------------


def test_preview_import_for_other_tenants_evaluation_returns_404(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = _create_evaluation(client, owner_a_headers, "Tenant A import RFP")

    response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements/import/preview",
        files=_csv_upload(),
        headers=owner_b_headers,
    )
    assert response.status_code == 404


def test_confirm_import_for_other_tenants_evaluation_returns_404(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = _create_evaluation(client, owner_a_headers, "Tenant A confirm import RFP")

    response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements/import/confirm",
        json={
            "requirements": [
                {
                    "dimension": "functional",
                    "category": "Core",
                    "title": "Req importado",
                    "description": "d",
                    "priority": "important",
                    "response_type": "text",
                    "weight": 40.0,
                    "required": False,
                    "display_order": 1,
                }
            ]
        },
        headers=owner_b_headers,
    )
    assert response.status_code == 404


def test_vendor_contact_cannot_use_import_endpoints(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    vendor_headers = bearer_headers_for(vendor_membership_id, mongo_test_settings)
    evaluation_id = _create_evaluation(client, owner_headers, "Vendor-blocked import RFP")

    preview_attempt = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements/import/preview",
        files=_csv_upload(),
        headers=vendor_headers,
    )
    assert preview_attempt.status_code == 403

    confirm_attempt = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements/import/confirm",
        json={"requirements": []},
        headers=vendor_headers,
    )
    assert confirm_attempt.status_code == 403
