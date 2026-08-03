import pytest
from azure.core.exceptions import ResourceNotFoundError

from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.service import AuditEventService
from procurawise.documents.antivirus import EICAR_SIGNATURE, StubAntivirusScanner
from procurawise.documents.repository import DocumentRepository
from procurawise.documents.service import (
    DocumentService,
    FileTooLargeError,
    InfectedFileError,
    UnsupportedFileTypeError,
)
from procurawise.evaluations.models import Evaluation
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.repository import MembershipRepository, TenantRepository, UserRepository
from procurawise.identity.service import IdentityService
from procurawise.proposals.exceptions import InvalidProposalTransitionError
from procurawise.proposals.models import Proposal
from procurawise.proposals.repository import ProposalRepository
from procurawise.shared.context import ActorContext
from procurawise.shared.mongo import get_database
from tests.conftest import unique_actor_by_role

pytestmark = pytest.mark.docker

_PDF_BYTES = b"%PDF-1.4 some real-looking pdf content"


@pytest.fixture(autouse=True)
def _clean_documents(mongo_test_db, documents_test_storage):
    yield
    mongo_test_db["documents"].delete_many({})
    mongo_test_db["evaluations"].delete_many({})
    mongo_test_db["proposals"].delete_many({})
    mongo_test_db["audit_events"].delete_many({})


def _vendor_actor(mongo_test_settings, membership_id: str) -> ActorContext:
    db = get_database(mongo_test_settings)
    identity_service = IdentityService(
        tenants=TenantRepository(db), users=UserRepository(db), memberships=MembershipRepository(db)
    )
    return identity_service.resolve_actor_context(membership_id)


def _create_draft_proposal(
    mongo_test_settings, tenant_id: str, vendor_org_id: str
) -> tuple[str, str]:
    db = get_database(mongo_test_settings)
    evaluations = EvaluationRepository(db)
    proposals = ProposalRepository(db)

    evaluation = Evaluation.create(tenant_id, "RFP con evidencia", "", "owner-membership")
    evaluations.insert(tenant_id, evaluation.to_document())

    proposal = Proposal.create(
        tenant_id=tenant_id, evaluation_id=evaluation.id, vendor_org_id=vendor_org_id
    )
    proposals.insert(tenant_id, proposal.to_document())
    return evaluation.id, proposal.id


def _build_service(
    mongo_test_settings, documents_test_settings, documents_test_storage
) -> DocumentService:
    db = get_database(mongo_test_settings)
    return DocumentService(
        documents=DocumentRepository(db),
        proposals=ProposalRepository(db),
        storage=documents_test_storage,
        scanner=StubAntivirusScanner(),
        audit=AuditEventService(AuditEventRepository(db), documents_test_settings),
        settings=documents_test_settings,
    )


def test_upload_clean_file_creates_document_and_blob(
    mongo_test_settings, documents_test_settings, documents_test_storage, seeded_actors
) -> None:
    tenant_id, membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    actor = _vendor_actor(mongo_test_settings, membership_id)
    evaluation_id, proposal_id = _create_draft_proposal(
        mongo_test_settings, tenant_id, actor.vendor_org_id
    )
    service = _build_service(mongo_test_settings, documents_test_settings, documents_test_storage)

    document = service.upload(
        tenant_id,
        actor.vendor_org_id,
        proposal_id,
        "req-1",
        "evidencia.pdf",
        _PDF_BYTES,
        actor=actor,
    )

    assert document.status == "current"
    assert document.version == 1
    assert document.evaluation_id == evaluation_id
    assert documents_test_storage.download(document.blob_key) == _PDF_BYTES

    listed = service.list_for_proposal(tenant_id, actor.vendor_org_id, proposal_id)
    assert [d.id for d in listed] == [document.id]


def test_upload_infected_file_is_rejected_without_persisting_anything(
    mongo_test_settings, documents_test_settings, documents_test_storage, seeded_actors
) -> None:
    tenant_id, membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    actor = _vendor_actor(mongo_test_settings, membership_id)
    _evaluation_id, proposal_id = _create_draft_proposal(
        mongo_test_settings, tenant_id, actor.vendor_org_id
    )
    service = _build_service(mongo_test_settings, documents_test_settings, documents_test_storage)
    infected_content = b"%PDF-1.4 " + EICAR_SIGNATURE

    with pytest.raises(InfectedFileError):
        service.upload(
            tenant_id,
            actor.vendor_org_id,
            proposal_id,
            None,
            "evidencia.pdf",
            infected_content,
            actor=actor,
        )

    assert service.list_for_proposal(tenant_id, actor.vendor_org_id, proposal_id) == []


def test_upload_rejects_disallowed_extension(
    mongo_test_settings, documents_test_settings, documents_test_storage, seeded_actors
) -> None:
    tenant_id, membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    actor = _vendor_actor(mongo_test_settings, membership_id)
    _evaluation_id, proposal_id = _create_draft_proposal(
        mongo_test_settings, tenant_id, actor.vendor_org_id
    )
    service = _build_service(mongo_test_settings, documents_test_settings, documents_test_storage)

    with pytest.raises(UnsupportedFileTypeError):
        service.upload(
            tenant_id, actor.vendor_org_id, proposal_id, None, "script.exe", b"MZ...", actor=actor
        )


def test_upload_rejects_oversized_file(
    mongo_test_settings, documents_test_settings, documents_test_storage, seeded_actors
) -> None:
    tenant_id, membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    actor = _vendor_actor(mongo_test_settings, membership_id)
    _evaluation_id, proposal_id = _create_draft_proposal(
        mongo_test_settings, tenant_id, actor.vendor_org_id
    )
    settings = documents_test_settings.model_copy(update={"documents_max_file_size_mb": 0})
    service = _build_service(mongo_test_settings, settings, documents_test_storage)

    with pytest.raises(FileTooLargeError):
        service.upload(
            tenant_id,
            actor.vendor_org_id,
            proposal_id,
            None,
            "evidencia.pdf",
            _PDF_BYTES,
            actor=actor,
        )


def test_replace_supersedes_prior_version_and_keeps_its_blob(
    mongo_test_settings, documents_test_settings, documents_test_storage, seeded_actors
) -> None:
    tenant_id, membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    actor = _vendor_actor(mongo_test_settings, membership_id)
    _evaluation_id, proposal_id = _create_draft_proposal(
        mongo_test_settings, tenant_id, actor.vendor_org_id
    )
    service = _build_service(mongo_test_settings, documents_test_settings, documents_test_storage)

    first = service.upload(
        tenant_id, actor.vendor_org_id, proposal_id, "req-1", "v1.pdf", _PDF_BYTES, actor=actor
    )
    second = service.upload(
        tenant_id, actor.vendor_org_id, proposal_id, "req-1", "v2.pdf", _PDF_BYTES, actor=actor
    )

    assert second.version == 2
    assert documents_test_storage.download(first.blob_key) == _PDF_BYTES

    all_versions = service.list_for_proposal(tenant_id, actor.vendor_org_id, proposal_id)
    by_id = {d.id: d for d in all_versions}
    assert by_id[first.id].status == "superseded"
    assert by_id[second.id].status == "current"


def test_download_url_and_delete_round_trip(
    mongo_test_settings, documents_test_settings, documents_test_storage, seeded_actors
) -> None:
    tenant_id, membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    actor = _vendor_actor(mongo_test_settings, membership_id)
    _evaluation_id, proposal_id = _create_draft_proposal(
        mongo_test_settings, tenant_id, actor.vendor_org_id
    )
    service = _build_service(mongo_test_settings, documents_test_settings, documents_test_storage)

    document = service.upload(
        tenant_id, actor.vendor_org_id, proposal_id, None, "brochure.pdf", _PDF_BYTES, actor=actor
    )

    url, expires_at = service.get_download_url(
        tenant_id, actor.vendor_org_id, proposal_id, document.id, actor=actor
    )
    assert url.startswith("http")
    assert expires_at is not None

    service.delete(tenant_id, actor.vendor_org_id, proposal_id, document.id, actor=actor)
    assert service.list_for_proposal(tenant_id, actor.vendor_org_id, proposal_id) == []
    with pytest.raises(ResourceNotFoundError):
        documents_test_storage.download(document.blob_key)


def test_upload_after_submit_is_rejected(
    mongo_test_settings,
    documents_test_settings,
    documents_test_storage,
    seeded_actors,
    mongo_test_db,
) -> None:
    tenant_id, membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    actor = _vendor_actor(mongo_test_settings, membership_id)
    _evaluation_id, proposal_id = _create_draft_proposal(
        mongo_test_settings, tenant_id, actor.vendor_org_id
    )
    mongo_test_db["proposals"].update_one({"_id": proposal_id}, {"$set": {"status": "submitted"}})
    service = _build_service(mongo_test_settings, documents_test_settings, documents_test_storage)

    with pytest.raises(InvalidProposalTransitionError):
        service.upload(
            tenant_id,
            actor.vendor_org_id,
            proposal_id,
            None,
            "evidencia.pdf",
            _PDF_BYTES,
            actor=actor,
        )
