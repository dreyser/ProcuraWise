"""Fase 23 acceptance criterion (backlog.md fila 23): "Cada reporte se genera
como job asincrono y sigue el contrato de polling." Exercises the full
Report generation pipeline against real Mongo + Azurite for all 8 deliverable
types (spec S10): readiness gating, request_generation -> queued,
process_generation_job -> succeeded (worker-equivalent call, same pattern
tests/integration/test_ai_service.py already uses for AIExecution), a real
downloadable blob per type, and idempotent retry."""

from datetime import UTC, datetime

import pytest

from procurawise.identity.dev_provider import DEV_ACTOR_HEADER
from procurawise.identity.models import Membership, User
from procurawise.identity.repository import MembershipRepository, UserRepository
from procurawise.reports.dependencies import build_report_service
from procurawise.reports.exceptions import InvalidReportFormatError, ReportNotReadyError
from procurawise.reports.models import VALID_FORMATS_BY_TYPE
from procurawise.shared.storage import AzureBlobStorage
from tests.conftest import (
    approve_and_publish,
    bearer_headers_for,
    unique_actor_by_role,
    vendor_bearer_headers_for,
)

pytestmark = pytest.mark.docker

_COMMERCIAL_KEYS = [
    "payment_terms",
    "price_protection",
    "contractual_flexibility",
    "discounts_incentives",
    "billing_transparency",
]
_RISK_KEYS = [
    "variable_cost_exposure",
    "increases_indexation",
    "assumptions_exclusions",
    "fx_fiscal_regulatory",
    "exit_portability_lockin",
]
_JUSTIFICATION = "El proveedor cumple todos los requisitos obligatorios y su TCO es el menor."

_SIGNATURE_BY_FORMAT = {
    "pdf": b"%PDF",
    "docx": b"PK\x03\x04",
    "xlsx": b"PK\x03\x04",
    "csv": None,  # validated by decoding/checking text content instead
}


def _max_scores_body() -> dict:
    return {
        "commercial_scores": [
            {"criterion_key": k, "score": 5, "comment": "Excelente"} for k in _COMMERCIAL_KEYS
        ],
        "risk_scores": [
            {"criterion_key": k, "score": 5, "comment": "Excelente"} for k in _RISK_KEYS
        ],
    }


def _create_approver(mongo_test_db, tenant_id: str) -> str:
    users = UserRepository(mongo_test_db)
    memberships = MembershipRepository(mongo_test_db)
    user = User.create(
        display_name="Aprobador Reportes", email="decision.approver.reports@dev.local"
    )
    users.insert(user.to_document())
    membership = Membership.create(tenant_id=tenant_id, user_id=user.id, role="approver")
    memberships.insert(membership.to_document())
    return membership.id


def _build_decided_evaluation(client, seeded_actors, mongo_test_settings, mongo_test_db) -> dict:
    """One evaluation, one requirement per gated dimension, one vendor
    proposal fully scored/assessed/TCO'd, one published Q&A exchange, and an
    *approved* Decision - the superset of readiness states every one of the
    8 report types needs to be exercisable in a single fixture."""
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    vendor_headers = vendor_bearer_headers_for(vendor_membership_id, mongo_test_settings)
    vendor_org_id = client.get(
        "/api/v1/me", headers={DEV_ACTOR_HEADER: vendor_membership_id}
    ).json()["vendor_org_id"]

    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Reportes RFP", "description": "Evaluacion de prueba para reportes"},
        headers=owner_headers,
    ).json()["id"]
    functional_id = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "functional",
            "category": "Core",
            "title": "Req funcional",
            "description": "d",
            "priority": "mandatory",
            "response_type": "text",
            "weight": 40.0,
            "required": False,
            "display_order": 1,
        },
        headers=owner_headers,
    ).json()["id"]
    technical_id = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "technical",
            "category": "Core",
            "title": "Req tecnico",
            "description": "d",
            "priority": "important",
            "response_type": "text",
            "weight": 20.0,
            "required": False,
            "display_order": 2,
        },
        headers=owner_headers,
    ).json()["id"]
    proposal_id = client.post(
        f"/api/v1/evaluations/{evaluation_id}/vendors",
        json={"vendor_org_id": vendor_org_id},
        headers=owner_headers,
    ).json()["id"]

    approver_membership_id = seeded_actors[(tenant_a, "approver")]
    approver_headers = bearer_headers_for(approver_membership_id, mongo_test_settings)
    approve_and_publish(
        client, owner_headers, approver_membership_id, approver_headers, evaluation_id
    )

    # Q&A exchange, while still collecting_responses.
    question_id = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/questions",
        json={"scope": "general", "requirement_id": None, "body": "Cual es el plazo de entrega?"},
        headers=vendor_headers,
    ).json()["id"]
    answer = client.put(
        f"/api/v1/evaluations/{evaluation_id}/questions/{question_id}/answer",
        json={
            "body": "30 dias naturales.",
            "visibility": "published_anonymized",
            "expected_version": 1,
        },
        headers=owner_headers,
    )
    assert answer.status_code == 200, answer.text

    cost_item = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/cost-items",
        json={
            "concept": "Licencia anual",
            "category": "recurring",
            "billing_unit": "usuario",
            "quantity": "10",
            "unit_price": "100",
            "currency": "MXN",
            "frequency_per_year": "1",
            "year_start": 1,
            "year_end": 1,
            "cost_type": "recurring",
            "expected_version": 1,
        },
        headers=vendor_headers,
    )
    assert cost_item.status_code == 200, cost_item.text
    submit = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/submit",
        json={"expected_version": cost_item.json()["version"]},
        headers=vendor_headers,
    )
    assert submit.status_code == 200, submit.text

    client.post(f"/api/v1/evaluations/{evaluation_id}/start-evaluation", headers=owner_headers)
    for requirement_id in (functional_id, technical_id):
        response = client.put(
            f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/scores/{requirement_id}",
            json={"score": 5, "comment": None},
            headers=owner_headers,
        )
        assert response.status_code == 200, response.text
    economic = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/economic-assessment",
        json=_max_scores_body(),
        headers=owner_headers,
    )
    assert economic.status_code == 200, economic.text
    complete = client.post(f"/api/v1/evaluations/{evaluation_id}/complete", headers=owner_headers)
    assert complete.status_code == 200, complete.text

    decision_approver_id = _create_approver(mongo_test_db, tenant_a)
    decision_approver_headers = bearer_headers_for(decision_approver_id, mongo_test_settings)
    client.post(f"/api/v1/evaluations/{evaluation_id}/decision", headers=owner_headers)
    client.patch(
        f"/api/v1/evaluations/{evaluation_id}/decision",
        json={
            "outcome": "selected",
            "selected_vendor_org_id": vendor_org_id,
            "justification": _JUSTIFICATION,
        },
        headers=owner_headers,
    )
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/decision/approver",
        json={"approver_membership_id": decision_approver_id},
        headers=owner_headers,
    )
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/decision/request-approval", headers=owner_headers
    )
    approve = client.post(
        f"/api/v1/evaluations/{evaluation_id}/decision/approve",
        json={},
        headers=decision_approver_headers,
    )
    assert approve.status_code == 200, approve.text

    return {
        "tenant_id": tenant_a,
        "evaluation_id": evaluation_id,
        "owner_membership_id": seeded_actors[(tenant_a, "evaluation_owner")],
    }


def _actor_context(seeded_actors, mongo_test_settings, membership_id: str):
    from procurawise.identity.repository import (
        MembershipRepository,
        TenantRepository,
        UserRepository,
    )
    from procurawise.identity.service import IdentityService
    from procurawise.shared.mongo import get_database

    db = get_database(mongo_test_settings)
    identity = IdentityService(
        tenants=TenantRepository(db), users=UserRepository(db), memberships=MembershipRepository(db)
    )
    return identity.resolve_actor_context(membership_id)


@pytest.fixture(autouse=True)
def _clean_reports(mongo_test_db):
    yield
    mongo_test_db["reports"].delete_many({})


def test_all_eight_report_types_generate_a_real_downloadable_file(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    ctx = _build_decided_evaluation(client, seeded_actors, mongo_test_settings, mongo_test_db)
    actor = _actor_context(seeded_actors, mongo_test_settings, ctx["owner_membership_id"])
    service = build_report_service(mongo_test_settings)
    storage = AzureBlobStorage.from_settings(
        mongo_test_settings, container_name=mongo_test_settings.reports_container_name
    )

    for report_type, formats in VALID_FORMATS_BY_TYPE.items():
        for format_ in formats:
            report = service.request_generation(
                ctx["tenant_id"],
                ctx["evaluation_id"],
                report_type=report_type,
                format=format_,
                actor=actor,
            )
            assert report.status == "queued"

            service.process_generation_job(ctx["tenant_id"], ctx["evaluation_id"], report.id)

            result = service.get_report(ctx["tenant_id"], ctx["evaluation_id"], report.id)
            assert result.status == "succeeded", (report_type, format_, result.error)
            assert result.blob_key is not None
            assert result.size_bytes is not None and result.size_bytes > 0

            url, expires_at = service.get_download_url(
                ctx["tenant_id"], ctx["evaluation_id"], report.id, actor=actor
            )
            assert url.startswith("http")
            assert expires_at > datetime.now(UTC)

            content = storage.download(result.blob_key)
            signature = _SIGNATURE_BY_FORMAT[format_]
            if signature is not None:
                assert content.startswith(signature), (report_type, format_)
            else:
                assert len(content) > 0


def test_process_generation_job_is_idempotent_on_retry(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    ctx = _build_decided_evaluation(client, seeded_actors, mongo_test_settings, mongo_test_db)
    actor = _actor_context(seeded_actors, mongo_test_settings, ctx["owner_membership_id"])
    service = build_report_service(mongo_test_settings)

    report = service.request_generation(
        ctx["tenant_id"],
        ctx["evaluation_id"],
        report_type="qna_summary",
        format="pdf",
        actor=actor,
    )
    service.process_generation_job(ctx["tenant_id"], ctx["evaluation_id"], report.id)
    first = service.get_report(ctx["tenant_id"], ctx["evaluation_id"], report.id)
    assert first.status == "succeeded"

    # A redelivered message for an already-processed report must be a
    # no-op, not a duplicate blob or an error (ADR 0005 idempotency).
    service.process_generation_job(ctx["tenant_id"], ctx["evaluation_id"], report.id)
    second = service.get_report(ctx["tenant_id"], ctx["evaluation_id"], report.id)
    assert second.blob_key == first.blob_key
    assert second.completed_at == first.completed_at


def test_decision_record_is_blocked_before_the_decision_is_approved(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    tenant_a, _vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Not decided yet RFP", "description": ""},
        headers=owner_headers,
    ).json()["id"]
    actor = _actor_context(
        seeded_actors, mongo_test_settings, seeded_actors[(tenant_a, "evaluation_owner")]
    )
    service = build_report_service(mongo_test_settings)

    readiness = service.readiness(tenant_a, evaluation_id, "decision_record")
    assert readiness["can_generate"] is False

    with pytest.raises(ReportNotReadyError):
        service.request_generation(
            tenant_a, evaluation_id, report_type="decision_record", format="pdf", actor=actor
        )


def test_vendor_comparison_is_blocked_while_evaluation_is_draft(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Draft RFP", "description": ""},
        headers=owner_headers,
    ).json()["id"]
    actor = _actor_context(
        seeded_actors, mongo_test_settings, seeded_actors[(tenant_a, "evaluation_owner")]
    )
    service = build_report_service(mongo_test_settings)

    with pytest.raises(ReportNotReadyError):
        service.request_generation(
            tenant_a, evaluation_id, report_type="vendor_comparison", format="pdf", actor=actor
        )

    # rfp_document/requirements_matrix/qna_summary are available even in draft.
    readiness = service.readiness(tenant_a, evaluation_id, "rfp_document")
    assert readiness["can_generate"] is True


def test_invalid_format_for_report_type_is_rejected(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Bad Format RFP", "description": ""},
        headers=owner_headers,
    ).json()["id"]
    actor = _actor_context(
        seeded_actors, mongo_test_settings, seeded_actors[(tenant_a, "evaluation_owner")]
    )
    service = build_report_service(mongo_test_settings)

    with pytest.raises(InvalidReportFormatError):
        service.request_generation(
            tenant_a, evaluation_id, report_type="vendor_comparison", format="xlsx", actor=actor
        )
