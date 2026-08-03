from procurawise.documents.models import Document, build_blob_key, sanitize_filename


def test_sanitize_filename_strips_path_separators() -> None:
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("C:\\Users\\evil\\cert.pdf") == "cert.pdf"


def test_sanitize_filename_replaces_unsafe_characters() -> None:
    assert sanitize_filename('cert&#"file (v2).PDF') == "cert_file_v2_.PDF"


def test_sanitize_filename_never_returns_empty() -> None:
    assert sanitize_filename("***///") == "documento"


def test_sanitize_filename_caps_length() -> None:
    long_name = "a" * 500 + ".pdf"
    assert len(sanitize_filename(long_name)) == 150


def test_build_blob_key_is_namespaced_and_versioned() -> None:
    key = build_blob_key("t1", "p1", "doc1", 2, "cert.pdf")
    assert key == "t1/p1/doc1/v2/cert.pdf"


def test_document_create_round_trips_through_document() -> None:
    document = Document.create(
        tenant_id="t1",
        evaluation_id="e1",
        proposal_id="p1",
        vendor_org_id="v1",
        requirement_id="r1",
        version=1,
        filename="evidencia.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        sha256="abc123",
        uploaded_by_membership_id="m1",
    )
    assert document.status == "current"
    assert document.scan_status == "clean"
    assert document.blob_key == f"t1/p1/{document.id}/v1/evidencia.pdf"

    restored = Document.from_document(document.to_document())
    assert restored == document


def test_document_create_supports_general_attachment_without_requirement() -> None:
    document = Document.create(
        tenant_id="t1",
        evaluation_id="e1",
        proposal_id="p1",
        vendor_org_id="v1",
        requirement_id=None,
        version=1,
        filename="brochure.pdf",
        content_type="application/pdf",
        size_bytes=2048,
        sha256="def456",
        uploaded_by_membership_id="m1",
    )
    assert document.requirement_id is None
