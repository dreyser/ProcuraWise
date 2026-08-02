import pytest

from procurawise.ai.curated_source_provider import CuratedSourceProvider
from procurawise.ai.research_provider import DiscoveryQuery
from procurawise.curated_sources.models import CuratedSource
from procurawise.curated_sources.repository import CuratedSourceRepository

pytestmark = pytest.mark.docker


@pytest.fixture(autouse=True)
def _clean_collection(mongo_test_db):
    yield
    mongo_test_db["curated_sources"].drop()


def _insert(repository: CuratedSourceRepository, **overrides) -> CuratedSource:  # noqa: ANN003
    defaults = {
        "title": "Gartner ERP guide",
        "url": "https://example.com/erp-guide",
        "summary": "Guía curada de criterios para evaluar ERP en la nube",
        "tags": ["erp"],
        "created_by_admin_id": "admin-1",
    }
    defaults.update(overrides)
    source = CuratedSource.create(**defaults)
    repository.insert(source.to_document())
    return source


def test_discover_returns_only_active_sources(mongo_test_db) -> None:
    repository = CuratedSourceRepository(mongo_test_db)
    active = _insert(repository, title="Active guide", summary="cloud erp evaluation criteria")
    inactive = _insert(repository, title="Inactive guide", summary="cloud erp evaluation criteria")
    repository.set_active(inactive.id, False)

    provider = CuratedSourceProvider(repository)
    result = provider.discover(
        "tenant-a", DiscoveryQuery(dimension="functional", description="cloud erp evaluation")
    )

    source_ids = {snippet.source_id for snippet in result.snippets}
    assert active.id in source_ids
    assert inactive.id not in source_ids


def test_discover_is_tenant_agnostic(mongo_test_db) -> None:
    repository = CuratedSourceRepository(mongo_test_db)
    source = _insert(repository, summary="cloud erp evaluation criteria")

    provider = CuratedSourceProvider(repository)
    for tenant_id in ("tenant-a", "tenant-b"):
        result = provider.discover(
            tenant_id, DiscoveryQuery(dimension="functional", description="cloud erp evaluation")
        )
        assert source.id in {snippet.source_id for snippet in result.snippets}


def test_discover_never_returns_url_as_content_only_as_url_field(mongo_test_db) -> None:
    repository = CuratedSourceRepository(mongo_test_db)
    _insert(repository, summary="cloud erp evaluation criteria")

    provider = CuratedSourceProvider(repository)
    result = provider.discover(
        "tenant-a", DiscoveryQuery(dimension="functional", description="cloud erp evaluation")
    )

    snippet = result.snippets[0]
    assert snippet.content == "cloud erp evaluation criteria"
    assert snippet.url == "https://example.com/erp-guide"
    assert snippet.source_type == "curated_source"
