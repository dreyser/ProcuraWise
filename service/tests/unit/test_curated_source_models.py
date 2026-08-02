from procurawise.curated_sources.models import CuratedSource


def test_create_defaults_to_active() -> None:
    source = CuratedSource.create(
        title="Gartner ERP guide",
        url="https://example.com/erp-guide",
        summary="Resumen curado de criterios de evaluacion de ERP",
        tags=["erp", "functional"],
        created_by_admin_id="admin-1",
    )
    assert source.active is True
    assert source.created_at == source.updated_at


def test_round_trip_through_document() -> None:
    source = CuratedSource.create(
        title="T", url="https://x", summary="S", tags=["a", "b"], created_by_admin_id="admin-1"
    )
    restored = CuratedSource.from_document(source.to_document())
    assert restored == source
