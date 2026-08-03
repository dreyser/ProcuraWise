import urllib.parse
import urllib.request
from urllib.error import HTTPError

import pytest

from procurawise.shared.storage import AzureBlobStorage

pytestmark = pytest.mark.docker


def test_generate_download_url_produces_a_real_downloadable_link(
    documents_test_storage: AzureBlobStorage,
) -> None:
    blob_name = "probe/evidence.pdf"
    content = b"%PDF-1.4 fake pdf content"
    documents_test_storage.upload(blob_name, content, content_type="application/pdf")

    url = documents_test_storage.generate_download_url(
        blob_name, expires_in_minutes=5, filename="evidence.pdf", content_type="application/pdf"
    )

    with urllib.request.urlopen(url) as response:  # noqa: S310 - test-only, Azurite URL
        assert response.status == 200
        assert response.read() == content
        assert response.headers.get("Content-Disposition") == 'attachment; filename="evidence.pdf"'
        assert response.headers.get("Content-Type") == "application/pdf"


def test_generate_download_url_expired_is_rejected(
    documents_test_storage: AzureBlobStorage,
) -> None:
    blob_name = "probe/expired.pdf"
    documents_test_storage.upload(blob_name, b"content", content_type="application/pdf")

    expired_url = documents_test_storage.generate_download_url(
        blob_name, expires_in_minutes=-5, filename="expired.pdf", content_type="application/pdf"
    )

    with pytest.raises(HTTPError) as exc_info:
        urllib.request.urlopen(expired_url)  # noqa: S310 - test-only, Azurite URL
    assert exc_info.value.code in (403, 409)


def test_generate_download_url_signs_read_only_permission(
    documents_test_storage: AzureBlobStorage,
) -> None:
    """Asserts the *signed* permission is read-only (`sp=r`), not that a
    write attempt against the URL is rejected - verified separately,
    Azurite 3.33.0 does not enforce the `sp=` permission scope on writes
    the way real Azure Blob Storage does (a `PUT` through a read-only SAS
    succeeds against Azurite, confirmed empirically during Fase 16). This is
    a known Azurite/Azure fidelity gap, not a bug in
    generate_download_url - the token itself is correctly scoped, real
    Azure Blob Storage is the actual enforcement boundary in production."""
    blob_name = "probe/read-only.pdf"
    documents_test_storage.upload(blob_name, b"original", content_type="application/pdf")

    url = documents_test_storage.generate_download_url(
        blob_name, expires_in_minutes=5, filename="read-only.pdf", content_type="application/pdf"
    )

    query = urllib.parse.urlparse(url).query
    params = urllib.parse.parse_qs(query)
    assert params["sp"] == ["r"]
