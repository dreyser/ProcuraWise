import pytest

from procurawise.shared.storage import AzureBlobStorage

pytestmark = pytest.mark.docker


def test_ensure_container_is_idempotent(blob_test_storage: AzureBlobStorage) -> None:
    # conftest's blob_test_storage fixture already called ensure_container() once;
    # calling it again must not raise.
    blob_test_storage.ensure_container()
    blob_test_storage.ensure_container()


def test_upload_read_delete_roundtrip(blob_test_storage: AzureBlobStorage) -> None:
    blob_name = "probe/test-file.txt"
    content = b"procurawise infra probe"

    blob_test_storage.upload(blob_name, content, content_type="text/plain")
    assert blob_test_storage.exists(blob_name) is True
    assert blob_test_storage.download(blob_name) == content

    blob_test_storage.delete(blob_name)
    assert blob_test_storage.exists(blob_name) is False
