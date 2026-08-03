import pytest

from procurawise.agreements.repository import AgreementRepository
from procurawise.agreements.service import AgreementService
from procurawise.documents.antivirus import EICAR_SIGNATURE
from procurawise.identity.dev_provider import DEV_ACTOR_HEADER
from procurawise.identity.models import Membership, User, VendorOrganization
from procurawise.identity.repository import (
    MembershipRepository,
    UserRepository,
    VendorOrganizationRepository,
)
from tests.conftest import (
    approve_and_publish,
    bearer_headers_for,
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
        json={"name": "RFP con evidencia", "description": ""},
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


def _create_second_vendor_contact_with_agreements(mongo_test_db, tenant_id: str) -> str:
    """Same shape as test_vendor_isolation.py's _create_second_vendor_contact
    - duplicated locally rather than cross-imported, matching this test
    suite's established per-file helper convention (see test_ai_service.py's
    own _create_draft_evaluation)."""
    users = UserRepository(mongo_test_db)
    vendor_orgs = VendorOrganizationRepository(mongo_test_db)
    memberships = MembershipRepository(mongo_test_db)
    user = User.create(display_name="Vendor Docs B", email="vendor.docs.b@dev.local")
    users.insert(user.to_document())
    vendor_org = VendorOrganization.create(tenant_id=tenant_id, name="Proveedor Documentos Dos")
    vendor_orgs.insert(tenant_id, vendor_org.to_document())
    membership = Membership.create(
        tenant_id=tenant_id, user_id=user.id, role="vendor_contact", vendor_org_id=vendor_org.id
    )
    memberships.insert(membership.to_document())

    agreements = AgreementService(AgreementRepository(mongo_test_db))
    for agreement_type in ("nda", "conflict_of_interest"):
        agreements.accept(
            tenant_id, user.id, membership.id, agreement_type, ip="127.0.0.1", user_agent="test"
        )
    return membership.id


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
        "vendor_org_id": vendor_org_id,
        "evaluation_id": evaluation_id,
        "proposal_id": proposal_id,
    }


def _documents_url(proposal_id: str, suffix: str = "") -> str:
    return f"/api/v1/vendor-portal/proposals/{proposal_id}/documents{suffix}"


def test_vendor_without_agreements_is_blocked_from_documents(
    client, vendor_setup, mongo_test_db, mongo_test_settings
) -> None:
    # Fase 16: the new document endpoints hang off the same
    # require_agreements_accepted dependency every vendor_portal/proposals
    # route already uses (Fase 15) - the gate itself was not re-implemented,
    # but this proves it was actually inherited, not silently bypassed.
    users = UserRepository(mongo_test_db)
    vendor_orgs = VendorOrganizationRepository(mongo_test_db)
    memberships = MembershipRepository(mongo_test_db)
    user = User.create(
        display_name="No Agreements Docs Vendor", email="no.agreements.docs@dev.local"
    )
    users.insert(user.to_document())
    vendor_org = VendorOrganization.create(
        tenant_id=vendor_setup["tenant_id"], name="Proveedor Sin Agreements Docs"
    )
    vendor_orgs.insert(vendor_setup["tenant_id"], vendor_org.to_document())
    membership = Membership.create(
        tenant_id=vendor_setup["tenant_id"],
        user_id=user.id,
        role="vendor_contact",
        vendor_org_id=vendor_org.id,
    )
    memberships.insert(membership.to_document())
    headers = vendor_bearer_headers_for(membership.id, mongo_test_settings)

    response = client.post(
        _documents_url(vendor_setup["proposal_id"]),
        files={"file": ("evidencia.pdf", _PDF_BYTES, "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 403
    assert response.json()["detail"]["detail"] == "agreements_required"


def test_upload_creates_and_lists_document(client, vendor_setup) -> None:
    proposal_id = vendor_setup["proposal_id"]
    headers = vendor_setup["vendor_headers"]

    upload = client.post(
        _documents_url(proposal_id),
        files={"file": ("evidencia.pdf", _PDF_BYTES, "application/pdf")},
        headers=headers,
    )
    assert upload.status_code == 201, upload.text
    body = upload.json()
    assert body["status"] == "current"
    assert body["version"] == 1
    assert body["filename"] == "evidencia.pdf"

    listing = client.get(_documents_url(proposal_id), headers=headers)
    assert listing.status_code == 200
    assert [d["id"] for d in listing.json()["items"]] == [body["id"]]


def test_download_url_then_delete(client, vendor_setup) -> None:
    proposal_id = vendor_setup["proposal_id"]
    headers = vendor_setup["vendor_headers"]
    document_id = client.post(
        _documents_url(proposal_id),
        files={"file": ("brochure.pdf", _PDF_BYTES, "application/pdf")},
        headers=headers,
    ).json()["id"]

    download = client.get(
        _documents_url(proposal_id, f"/{document_id}/download-url"), headers=headers
    )
    assert download.status_code == 200
    payload = download.json()
    assert payload["url"].startswith("http")
    assert "expires_at" in payload

    delete = client.delete(_documents_url(proposal_id, f"/{document_id}"), headers=headers)
    assert delete.status_code == 204

    listing = client.get(_documents_url(proposal_id), headers=headers)
    assert listing.json()["items"] == []


def test_replace_increments_version(client, vendor_setup) -> None:
    proposal_id = vendor_setup["proposal_id"]
    headers = vendor_setup["vendor_headers"]

    first = client.post(
        _documents_url(proposal_id),
        files={"file": ("v1.pdf", _PDF_BYTES, "application/pdf")},
        data={"requirement_id": "req-slot"},
        headers=headers,
    ).json()
    second = client.post(
        _documents_url(proposal_id),
        files={"file": ("v2.pdf", _PDF_BYTES, "application/pdf")},
        data={"requirement_id": "req-slot"},
        headers=headers,
    ).json()

    assert first["version"] == 1
    assert second["version"] == 2

    listing = client.get(_documents_url(proposal_id), headers=headers).json()["items"]
    by_id = {d["id"]: d for d in listing}
    assert by_id[first["id"]]["status"] == "superseded"
    assert by_id[second["id"]]["status"] == "current"


def test_upload_rejects_oversized_file(client, vendor_setup) -> None:
    proposal_id = vendor_setup["proposal_id"]
    headers = vendor_setup["vendor_headers"]
    oversized = b"%" * (26 * 1024 * 1024)

    response = client.post(
        _documents_url(proposal_id),
        files={"file": ("grande.pdf", oversized, "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 413


def test_upload_rejects_disallowed_extension(client, vendor_setup) -> None:
    proposal_id = vendor_setup["proposal_id"]
    headers = vendor_setup["vendor_headers"]

    response = client.post(
        _documents_url(proposal_id),
        files={"file": ("script.exe", b"MZ...", "application/octet-stream")},
        headers=headers,
    )
    assert response.status_code == 422


def test_upload_rejects_infected_file_without_leaking_reason(client, vendor_setup) -> None:
    proposal_id = vendor_setup["proposal_id"]
    headers = vendor_setup["vendor_headers"]

    response = client.post(
        _documents_url(proposal_id),
        files={"file": ("evidencia.pdf", b"%PDF-1.4 " + EICAR_SIGNATURE, "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 400
    assert "eicar" not in response.text.lower()
    assert "infect" not in response.text.lower()


def test_upload_and_delete_rejected_after_submit(client, vendor_setup) -> None:
    proposal_id = vendor_setup["proposal_id"]
    headers = vendor_setup["vendor_headers"]
    document_id = client.post(
        _documents_url(proposal_id),
        files={"file": ("evidencia.pdf", _PDF_BYTES, "application/pdf")},
        headers=headers,
    ).json()["id"]

    submit = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/submit",
        json={"expected_version": 1},
        headers=headers,
    )
    assert submit.status_code == 200

    upload_after_submit = client.post(
        _documents_url(proposal_id),
        files={"file": ("tarde.pdf", _PDF_BYTES, "application/pdf")},
        headers=headers,
    )
    assert upload_after_submit.status_code == 409

    delete_after_submit = client.delete(
        _documents_url(proposal_id, f"/{document_id}"), headers=headers
    )
    assert delete_after_submit.status_code == 409


def test_cross_vendor_cannot_see_upload_or_download_another_vendors_documents(
    client, vendor_setup, mongo_test_db, mongo_test_settings
) -> None:
    proposal_id = vendor_setup["proposal_id"]
    tenant_id = vendor_setup["tenant_id"]
    owner_headers = vendor_setup["vendor_headers"]
    document_id = client.post(
        _documents_url(proposal_id),
        files={"file": ("evidencia.pdf", _PDF_BYTES, "application/pdf")},
        headers=owner_headers,
    ).json()["id"]

    other_membership_id = _create_second_vendor_contact_with_agreements(mongo_test_db, tenant_id)
    other_headers = vendor_bearer_headers_for(other_membership_id, mongo_test_settings)

    assert client.get(_documents_url(proposal_id), headers=other_headers).status_code == 404
    assert (
        client.get(
            _documents_url(proposal_id, f"/{document_id}/download-url"), headers=other_headers
        ).status_code
        == 404
    )
    assert (
        client.post(
            _documents_url(proposal_id),
            files={"file": ("intruso.pdf", _PDF_BYTES, "application/pdf")},
            headers=other_headers,
        ).status_code
        == 404
    )
    assert (
        client.delete(
            _documents_url(proposal_id, f"/{document_id}"), headers=other_headers
        ).status_code
        == 404
    )

    # Sanity check: the real owner still sees it (isolation is real, not an
    # always-404 bug).
    assert client.get(_documents_url(proposal_id), headers=owner_headers).status_code == 200


def test_uploaded_document_audit_events_never_contain_url_or_content(
    client, vendor_setup, mongo_test_db
) -> None:
    proposal_id = vendor_setup["proposal_id"]
    headers = vendor_setup["vendor_headers"]
    document_id = client.post(
        _documents_url(proposal_id),
        files={"file": ("evidencia.pdf", _PDF_BYTES, "application/pdf")},
        headers=headers,
    ).json()["id"]
    download_url = client.get(
        _documents_url(proposal_id, f"/{document_id}/download-url"), headers=headers
    ).json()["url"]

    events = list(mongo_test_db["audit_events"].find({"resource_id": document_id}))
    actions = {e["action"] for e in events}
    assert "document_uploaded" in actions
    assert "document_download_url_issued" in actions
    for event in events:
        serialized = str(event)
        assert download_url not in serialized
        assert "evidencia real de RFP" not in serialized
