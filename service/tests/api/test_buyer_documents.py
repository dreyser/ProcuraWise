import pytest

from procurawise.identity.dev_provider import DEV_ACTOR_HEADER
from tests.conftest import (
    approve_and_publish,
    bearer_headers_for,
    tenant_ids,
    unique_actor_by_role,
    vendor_bearer_headers_for,
)

pytestmark = pytest.mark.docker

_PDF_BYTES = b"%PDF-1.4 evidencia real de RFP"


def _requirement_payload(dimension: str, weight: float) -> dict:
    return {
        "dimension": dimension,
        "category": "c",
        "title": f"{dimension} requirement",
        "description": "d",
        "priority": "important",
        "response_type": "text",
        "weight": weight,
        "required": False,
        "display_order": 1,
    }


def _create_draft_proposal(
    client,
    owner_headers: dict,
    vendor_org_id: str,
    *,
    seeded_actors,
    tenant_id,
    mongo_test_settings,
) -> tuple[str, str]:
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "RFP con evidencia (buyer)", "description": ""},
        headers=owner_headers,
    ).json()["id"]
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json=_requirement_payload("functional", 40.0),
        headers=owner_headers,
    )
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json=_requirement_payload("technical", 20.0),
        headers=owner_headers,
    )
    proposal_id = client.post(
        f"/api/v1/evaluations/{evaluation_id}/vendors",
        json={"vendor_org_id": vendor_org_id},
        headers=owner_headers,
    ).json()["id"]
    approver_membership_id = seeded_actors[(tenant_id, "approver")]
    approver_headers = bearer_headers_for(approver_membership_id, mongo_test_settings)
    approve_and_publish(
        client, owner_headers, approver_membership_id, approver_headers, evaluation_id
    )
    return evaluation_id, proposal_id


@pytest.fixture
def vendor_setup(client, seeded_actors, mongo_test_settings):
    tenant_id, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_id, "evaluation_owner")], mongo_test_settings
    )
    vendor_headers = vendor_bearer_headers_for(vendor_membership_id, mongo_test_settings)
    vendor_dev_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_dev_headers).json()["vendor_org_id"]
    evaluation_id, proposal_id = _create_draft_proposal(
        client,
        owner_headers,
        vendor_org_id,
        seeded_actors=seeded_actors,
        tenant_id=tenant_id,
        mongo_test_settings=mongo_test_settings,
    )
    return {
        "tenant_id": tenant_id,
        "owner_headers": owner_headers,
        "vendor_headers": vendor_headers,
        "evaluation_id": evaluation_id,
        "proposal_id": proposal_id,
    }


def _buyer_documents_url(evaluation_id: str, proposal_id: str, suffix: str = "") -> str:
    return f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/documents{suffix}"


def test_buyer_can_list_and_download_vendor_documents(client, vendor_setup) -> None:
    evaluation_id = vendor_setup["evaluation_id"]
    proposal_id = vendor_setup["proposal_id"]
    document_id = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/documents",
        files={"file": ("evidencia.pdf", _PDF_BYTES, "application/pdf")},
        headers=vendor_setup["vendor_headers"],
    ).json()["id"]

    listing = client.get(
        _buyer_documents_url(evaluation_id, proposal_id), headers=vendor_setup["owner_headers"]
    )
    assert listing.status_code == 200
    assert [d["id"] for d in listing.json()["items"]] == [document_id]

    download = client.get(
        _buyer_documents_url(evaluation_id, proposal_id, f"/{document_id}/download-url"),
        headers=vendor_setup["owner_headers"],
    )
    assert download.status_code == 200
    assert download.json()["url"].startswith("http")


def test_buyer_documents_router_is_read_only(client, vendor_setup) -> None:
    evaluation_id = vendor_setup["evaluation_id"]
    proposal_id = vendor_setup["proposal_id"]
    # No POST/DELETE is registered on the buyer router at all - the buyer
    # cannot even structurally reach an upload/delete path, unlike the
    # vendor router which 409s them post-submit. FastAPI 405s a path whose
    # prefix matches another router but whose method doesn't.
    response = client.post(
        _buyer_documents_url(evaluation_id, proposal_id),
        files={"file": ("intento.pdf", _PDF_BYTES, "application/pdf")},
        headers=vendor_setup["owner_headers"],
    )
    assert response.status_code in (404, 405)


def test_buyer_of_other_tenant_gets_404(
    client, vendor_setup, seeded_actors, mongo_test_settings
) -> None:
    evaluation_id = vendor_setup["evaluation_id"]
    proposal_id = vendor_setup["proposal_id"]
    client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/documents",
        files={"file": ("evidencia.pdf", _PDF_BYTES, "application/pdf")},
        headers=vendor_setup["vendor_headers"],
    )

    tenant_a, tenant_b = tenant_ids(seeded_actors)
    other_tenant_id = tenant_b if tenant_a == vendor_setup["tenant_id"] else tenant_a
    other_owner_headers = bearer_headers_for(
        seeded_actors[(other_tenant_id, "evaluation_owner")], mongo_test_settings
    )

    response = client.get(
        _buyer_documents_url(evaluation_id, proposal_id), headers=other_owner_headers
    )
    assert response.status_code == 404


def test_evaluation_id_mismatch_returns_404(client, vendor_setup) -> None:
    proposal_id = vendor_setup["proposal_id"]
    response = client.get(
        _buyer_documents_url("not-the-real-evaluation-id", proposal_id),
        headers=vendor_setup["owner_headers"],
    )
    assert response.status_code == 404


def test_submit_freezes_document_ids_into_snapshot(client, vendor_setup) -> None:
    evaluation_id = vendor_setup["evaluation_id"]
    proposal_id = vendor_setup["proposal_id"]
    vendor_headers = vendor_setup["vendor_headers"]
    document_id = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/documents",
        files={"file": ("evidencia.pdf", _PDF_BYTES, "application/pdf")},
        headers=vendor_headers,
    ).json()["id"]

    submit = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/submit",
        json={"expected_version": 1},
        headers=vendor_headers,
    )
    assert submit.status_code == 200

    detail = client.get(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}",
        headers=vendor_setup["owner_headers"],
    )
    assert detail.status_code == 200
    assert detail.json()["snapshots"][-1]["document_ids"] == [document_id]

    # The document remains readable/downloadable by the buyer after submit -
    # the snapshot only freezes *which* ids were current, the Document rows
    # themselves stay the source of truth (see documents/service.py).
    listing = client.get(
        _buyer_documents_url(evaluation_id, proposal_id), headers=vendor_setup["owner_headers"]
    )
    assert [d["id"] for d in listing.json()["items"]] == [document_id]
