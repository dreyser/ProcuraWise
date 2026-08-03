from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.service import AuditEventService
from procurawise.documents.antivirus import StubAntivirusScanner
from procurawise.documents.models import Document
from procurawise.documents.repository import DocumentRepository
from procurawise.documents.schemas import (
    DocumentDownloadUrlResponse,
    DocumentListResponse,
    DocumentResponse,
)
from procurawise.documents.service import (
    DocumentNotFoundError,
    DocumentService,
    EmptyFileError,
    FileTooLargeError,
    InfectedFileError,
    UnsupportedFileTypeError,
)
from procurawise.proposals.exceptions import InvalidProposalTransitionError, ProposalNotFoundError
from procurawise.proposals.repository import ProposalRepository
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext, require_role
from procurawise.shared.mongo import get_database
from procurawise.shared.roles import BUYER_READ_ROLES
from procurawise.shared.storage import AzureBlobStorage
from procurawise.vendor_portal.dependencies import require_agreements_accepted

vendor_documents_router = APIRouter(
    prefix="/vendor-portal/proposals/{proposal_id}/documents", tags=["vendor-portal-documents"]
)
buyer_documents_router = APIRouter(
    prefix="/evaluations/{evaluation_id}/proposals/{proposal_id}/documents",
    tags=["proposal-documents"],
)

require_buyer_read = require_role(*BUYER_READ_ROLES)

# Lazy, in-process container provisioning: no migration or startup hook
# creates the documents container today (`shared/migrations.py::run_migrations`
# is Mongo-index-only and never runs automatically - see its docstring), so
# the first request that needs Blob access creates it, once per (container
# name, process) - `ensure_container()` itself is idempotent, but skipping
# the round trip on every request avoids an unnecessary Blob call per upload.
_provisioned_containers: set[str] = set()


def get_document_service(settings: Settings = Depends(get_settings)) -> DocumentService:
    db = get_database(settings)
    storage = AzureBlobStorage.from_settings(
        settings, container_name=settings.documents_container_name
    )
    if settings.documents_container_name not in _provisioned_containers:
        storage.ensure_container()
        _provisioned_containers.add(settings.documents_container_name)
    return DocumentService(
        documents=DocumentRepository(db),
        proposals=ProposalRepository(db),
        storage=storage,
        scanner=StubAntivirusScanner(),
        audit=AuditEventService(AuditEventRepository(db), settings),
        settings=settings,
    )


def _document_response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        proposal_id=document.proposal_id,
        requirement_id=document.requirement_id,
        version=document.version,
        status=document.status,
        filename=document.filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        uploaded_by_membership_id=document.uploaded_by_membership_id,
        created_at=document.created_at,
    )


@vendor_documents_router.post("", response_model=DocumentResponse, status_code=201)
async def upload_document(
    proposal_id: str,
    file: Annotated[UploadFile, File()],
    requirement_id: Annotated[str | None, Form()] = None,
    context: ActorContext = Depends(require_agreements_accepted),
    service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    assert context.vendor_org_id is not None
    content = await file.read()
    filename = file.filename or "documento"
    try:
        document = service.upload(
            context.tenant_id,
            context.vendor_org_id,
            proposal_id,
            requirement_id,
            filename,
            content,
            actor=context,
        )
    except ProposalNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidProposalTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except FileTooLargeError:
        raise HTTPException(
            status_code=413, detail="file exceeds the maximum allowed size"
        ) from None
    except (EmptyFileError, UnsupportedFileTypeError):
        raise HTTPException(status_code=422, detail="unsupported or empty file") from None
    except InfectedFileError:
        # Deliberately generic - never reveal *why* to avoid helping an
        # attacker probe/evade the (stub) scanner. See documents plan §H.
        raise HTTPException(status_code=400, detail="file rejected") from None
    return _document_response(document)


@vendor_documents_router.get("", response_model=DocumentListResponse)
def list_documents(
    proposal_id: str,
    context: ActorContext = Depends(require_agreements_accepted),
    service: DocumentService = Depends(get_document_service),
) -> DocumentListResponse:
    assert context.vendor_org_id is not None
    try:
        documents = service.list_for_proposal(context.tenant_id, context.vendor_org_id, proposal_id)
    except ProposalNotFoundError:
        raise HTTPException(status_code=404) from None
    return DocumentListResponse(items=[_document_response(d) for d in documents])


@vendor_documents_router.get(
    "/{document_id}/download-url", response_model=DocumentDownloadUrlResponse
)
def get_download_url(
    proposal_id: str,
    document_id: str,
    context: ActorContext = Depends(require_agreements_accepted),
    service: DocumentService = Depends(get_document_service),
) -> DocumentDownloadUrlResponse:
    assert context.vendor_org_id is not None
    try:
        url, expires_at = service.get_download_url(
            context.tenant_id, context.vendor_org_id, proposal_id, document_id, actor=context
        )
    except (ProposalNotFoundError, DocumentNotFoundError):
        raise HTTPException(status_code=404) from None
    return DocumentDownloadUrlResponse(url=url, expires_at=expires_at)


@vendor_documents_router.delete("/{document_id}", status_code=204)
def delete_document(
    proposal_id: str,
    document_id: str,
    context: ActorContext = Depends(require_agreements_accepted),
    service: DocumentService = Depends(get_document_service),
) -> None:
    assert context.vendor_org_id is not None
    try:
        service.delete(
            context.tenant_id, context.vendor_org_id, proposal_id, document_id, actor=context
        )
    except ProposalNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidProposalTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except DocumentNotFoundError:
        raise HTTPException(status_code=404) from None


@buyer_documents_router.get("", response_model=DocumentListResponse)
def list_documents_as_buyer(
    evaluation_id: str,
    proposal_id: str,
    context: ActorContext = Depends(require_buyer_read),
    service: DocumentService = Depends(get_document_service),
) -> DocumentListResponse:
    try:
        documents = service.list_for_proposal_as_buyer(
            context.tenant_id, evaluation_id, proposal_id
        )
    except ProposalNotFoundError:
        raise HTTPException(status_code=404) from None
    return DocumentListResponse(items=[_document_response(d) for d in documents])


@buyer_documents_router.get(
    "/{document_id}/download-url", response_model=DocumentDownloadUrlResponse
)
def get_download_url_as_buyer(
    evaluation_id: str,
    proposal_id: str,
    document_id: str,
    context: ActorContext = Depends(require_buyer_read),
    service: DocumentService = Depends(get_document_service),
) -> DocumentDownloadUrlResponse:
    try:
        url, expires_at = service.get_download_url_as_buyer(
            context.tenant_id, evaluation_id, proposal_id, document_id, actor=context
        )
    except (ProposalNotFoundError, DocumentNotFoundError):
        raise HTTPException(status_code=404) from None
    return DocumentDownloadUrlResponse(url=url, expires_at=expires_at)
