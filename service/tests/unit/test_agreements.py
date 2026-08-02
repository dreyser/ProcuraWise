from unittest.mock import MagicMock

from procurawise.agreements import legal_content
from procurawise.agreements.models import Agreement
from procurawise.agreements.repository import AgreementRepository
from procurawise.agreements.service import AgreementService


def test_agreement_create_round_trips_through_document() -> None:
    agreement = Agreement.create(
        tenant_id="t1",
        user_id="u1",
        membership_id="m1",
        type="nda",
        version=legal_content.CURRENT_NDA_VERSION,
        ip="203.0.113.1",
        user_agent="pytest",
    )
    restored = Agreement.from_document(agreement.to_document())
    assert restored == agreement
    assert restored.ip == "203.0.113.1"


def test_has_current_acceptance_false_when_never_accepted() -> None:
    repository = MagicMock(spec=AgreementRepository)
    repository.find_latest.return_value = None
    service = AgreementService(repository)
    assert service.has_current_acceptance("t1", "u1", "nda") is False


def test_has_current_acceptance_false_when_version_is_stale() -> None:
    repository = MagicMock(spec=AgreementRepository)
    repository.find_latest.return_value = {"version": "old-version"}
    service = AgreementService(repository)
    assert service.has_current_acceptance("t1", "u1", "nda") is False


def test_has_current_acceptance_true_when_version_matches() -> None:
    repository = MagicMock(spec=AgreementRepository)
    repository.find_latest.return_value = {"version": legal_content.CURRENT_NDA_VERSION}
    service = AgreementService(repository)
    assert service.has_current_acceptance("t1", "u1", "nda") is True


def test_missing_agreement_types_lists_only_unmet_types() -> None:
    repository = MagicMock(spec=AgreementRepository)

    def _find_latest(tenant_id: str, user_id: str, agreement_type: str) -> dict | None:
        if agreement_type == "nda":
            return {"version": legal_content.CURRENT_NDA_VERSION}
        return None

    repository.find_latest.side_effect = _find_latest
    service = AgreementService(repository)
    assert service.missing_agreement_types("t1", "u1") == ["conflict_of_interest"]


def test_accept_persists_current_version_and_returns_it() -> None:
    repository = MagicMock(spec=AgreementRepository)
    service = AgreementService(repository)

    agreement = service.accept(
        "t1", "u1", "m1", "conflict_of_interest", ip="203.0.113.1", user_agent="pytest"
    )

    assert agreement.version == legal_content.CURRENT_CONFLICT_OF_INTEREST_VERSION
    repository.insert.assert_called_once()
    inserted_tenant_id, inserted_doc = repository.insert.call_args[0]
    assert inserted_tenant_id == "t1"
    assert inserted_doc["type"] == "conflict_of_interest"
    assert inserted_doc["ip"] == "203.0.113.1"
