import hashlib
from datetime import UTC, datetime, timedelta

from procurawise.audit.service import AuditEventService
from procurawise.documents.antivirus import AntivirusScanner
from procurawise.documents.models import Document
from procurawise.documents.repository import DocumentRepository
from procurawise.proposals.exceptions import InvalidProposalTransitionError, ProposalNotFoundError
from procurawise.proposals.models import Proposal
from procurawise.proposals.repository import ProposalRepository
from procurawise.shared.config import Settings
from procurawise.shared.context import ActorContext
from procurawise.shared.storage import BlobStorage

# Fase 16 planning §D: extension is the primary classifier (mapped to the
# canonical content_type this service persists, never the client's declared
# Content-Type header, which is untrustworthy input on its own); magic bytes
# cross-check the ones with a reliable signature. No dependency added for
# this (no python-magic/libmagic) - a short, explicit table is enough for a
# deliberately small allowlist.
ALLOWED_EXTENSIONS: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "csv": "text/csv",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "txt": "text/plain",
}

_OOXML_SIGNATURE = (b"PK\x03\x04",)
_MAGIC_BYTES: dict[str, tuple[bytes, ...]] = {
    "application/pdf": (b"%PDF-",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": _OOXML_SIGNATURE,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": _OOXML_SIGNATURE,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": _OOXML_SIGNATURE,
    # csv/txt are arbitrary text with no reliable signature - extension is
    # the only signal for those two, deliberately.
}


class DocumentNotFoundError(Exception):
    """No Document exists for this id within the caller's tenant/proposal
    scope (or, for the vendor-side service methods, vendor_org_id scope)."""


class EmptyFileError(Exception):
    pass


class FileTooLargeError(Exception):
    pass


class UnsupportedFileTypeError(Exception):
    """Extension not in the allowlist, or its declared extension does not
    match the file's actual magic bytes."""


class InfectedFileError(Exception):
    """The stub (or, in the future, a real) AntivirusScanner flagged this
    content - never distinguished further to the HTTP caller beyond a
    generic rejection, to avoid revealing scanner internals."""


def _validate_and_classify(filename: str, content: bytes, max_size_bytes: int) -> str:
    """Returns the canonical content_type to persist - never the client's
    declared Content-Type, which this function does not even look at."""
    if len(content) == 0:
        raise EmptyFileError()
    if len(content) > max_size_bytes:
        raise FileTooLargeError()

    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    content_type = ALLOWED_EXTENSIONS.get(extension)
    if content_type is None:
        raise UnsupportedFileTypeError(extension)

    signatures = _MAGIC_BYTES.get(content_type)
    if signatures and not any(content.startswith(sig) for sig in signatures):
        raise UnsupportedFileTypeError(extension)

    return content_type


class DocumentService:
    """Fase 16: orchestrates validation -> AV stub -> Blob upload -> Mongo
    metadata, in that order (Blob write first, Mongo insert second - a
    failure between the two leaves an orphaned, inaccessible blob rather
    than a Document row pointing at bytes that were never written; see
    planning §D "fallo parcial"). Never persists anything for a rejected
    (infected/oversized/wrong-type) upload."""

    def __init__(
        self,
        documents: DocumentRepository,
        proposals: ProposalRepository,
        storage: BlobStorage,
        scanner: AntivirusScanner,
        audit: AuditEventService,
        settings: Settings,
    ) -> None:
        self._documents = documents
        self._proposals = proposals
        self._storage = storage
        self._scanner = scanner
        self._audit = audit
        self._settings = settings

    def _get_proposal(self, tenant_id: str, proposal_id: str) -> Proposal:
        doc = self._proposals.find_by_id(tenant_id, proposal_id)
        if doc is None:
            raise ProposalNotFoundError(proposal_id)
        return Proposal.from_document(doc)

    def _get_vendor_proposal(
        self, tenant_id: str, vendor_org_id: str, proposal_id: str
    ) -> Proposal:
        proposal = self._get_proposal(tenant_id, proposal_id)
        if proposal.vendor_org_id != vendor_org_id:
            # Same vendor cannot see another vendor's proposal - collapses to
            # the same ProposalNotFoundError/404 as "does not exist at all",
            # never confirming existence.
            raise ProposalNotFoundError(proposal_id)
        return proposal

    def upload(
        self,
        tenant_id: str,
        vendor_org_id: str,
        proposal_id: str,
        requirement_id: str | None,
        filename: str,
        content: bytes,
        *,
        actor: ActorContext,
    ) -> Document:
        proposal = self._get_vendor_proposal(tenant_id, vendor_org_id, proposal_id)
        if proposal.status != "draft":
            raise InvalidProposalTransitionError("proposal is not draft")

        content_type = _validate_and_classify(
            filename, content, self._settings.documents_max_file_size_mb * 1024 * 1024
        )

        scan = self._scanner.scan(content)
        if not scan.clean:
            self._audit.record(
                tenant_id=tenant_id,
                actor=actor,
                action="document_upload_rejected",
                resource_type="document",
                resource_id=proposal_id,
                evaluation_id=proposal.evaluation_id,
                proposal_id=proposal_id,
                metadata={"reason": "infected"},
            )
            raise InfectedFileError()

        existing_current: Document | None = None
        version = 1
        if requirement_id is not None:
            existing_doc = self._documents.find_current_for_slot(
                tenant_id, proposal_id, requirement_id
            )
            if existing_doc is not None:
                existing_current = Document.from_document(existing_doc)
                version = existing_current.version + 1

        document = Document.create(
            tenant_id=tenant_id,
            evaluation_id=proposal.evaluation_id,
            proposal_id=proposal_id,
            vendor_org_id=vendor_org_id,
            requirement_id=requirement_id,
            version=version,
            filename=filename,
            content_type=content_type,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            uploaded_by_membership_id=actor.membership_id,
        )
        self._storage.upload(document.blob_key, content, content_type=content_type)
        self._documents.insert(tenant_id, document.to_document())
        if existing_current is not None:
            self._documents.mark_superseded(tenant_id, existing_current.id)

        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="document_replaced" if existing_current is not None else "document_uploaded",
            resource_type="document",
            resource_id=document.id,
            evaluation_id=proposal.evaluation_id,
            proposal_id=proposal_id,
            metadata={
                "filename": document.filename,
                "size_bytes": document.size_bytes,
                "requirement_id": requirement_id,
                "version": version,
            },
        )
        return document

    def list_for_proposal(
        self, tenant_id: str, vendor_org_id: str, proposal_id: str
    ) -> list[Document]:
        self._get_vendor_proposal(tenant_id, vendor_org_id, proposal_id)
        return [
            Document.from_document(d)
            for d in self._documents.list_for_proposal(tenant_id, proposal_id)
        ]

    def _get_buyer_proposal(self, tenant_id: str, evaluation_id: str, proposal_id: str) -> Proposal:
        proposal = self._get_proposal(tenant_id, proposal_id)
        if proposal.evaluation_id != evaluation_id:
            raise ProposalNotFoundError(proposal_id)
        return proposal

    def list_for_proposal_as_buyer(
        self, tenant_id: str, evaluation_id: str, proposal_id: str
    ) -> list[Document]:
        self._get_buyer_proposal(tenant_id, evaluation_id, proposal_id)
        return [
            Document.from_document(d)
            for d in self._documents.list_for_proposal(tenant_id, proposal_id)
        ]

    def _resolve_document(self, tenant_id: str, proposal_id: str, document_id: str) -> Document:
        doc = self._documents.find_by_id(tenant_id, document_id)
        if doc is None or doc["proposal_id"] != proposal_id:
            raise DocumentNotFoundError(document_id)
        return Document.from_document(doc)

    def get_download_url(
        self,
        tenant_id: str,
        vendor_org_id: str,
        proposal_id: str,
        document_id: str,
        *,
        actor: ActorContext,
    ) -> tuple[str, datetime]:
        self._get_vendor_proposal(tenant_id, vendor_org_id, proposal_id)
        return self._issue_download_url(tenant_id, proposal_id, document_id, actor=actor)

    def get_download_url_as_buyer(
        self,
        tenant_id: str,
        evaluation_id: str,
        proposal_id: str,
        document_id: str,
        *,
        actor: ActorContext,
    ) -> tuple[str, datetime]:
        self._get_buyer_proposal(tenant_id, evaluation_id, proposal_id)
        return self._issue_download_url(tenant_id, proposal_id, document_id, actor=actor)

    def _issue_download_url(
        self, tenant_id: str, proposal_id: str, document_id: str, *, actor: ActorContext
    ) -> tuple[str, datetime]:
        document = self._resolve_document(tenant_id, proposal_id, document_id)
        ttl_minutes = self._settings.documents_download_url_ttl_minutes
        url = self._storage.generate_download_url(
            document.blob_key,
            expires_in_minutes=ttl_minutes,
            filename=document.filename,
            content_type=document.content_type,
        )
        expires_at = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
        # Never the URL itself in metadata (it embeds a valid signature) -
        # only the fact that one was issued, for whom, and for which document.
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="document_download_url_issued",
            resource_type="document",
            resource_id=document.id,
            evaluation_id=document.evaluation_id,
            proposal_id=proposal_id,
        )
        return url, expires_at

    def delete(
        self,
        tenant_id: str,
        vendor_org_id: str,
        proposal_id: str,
        document_id: str,
        *,
        actor: ActorContext,
    ) -> None:
        proposal = self._get_vendor_proposal(tenant_id, vendor_org_id, proposal_id)
        if proposal.status != "draft":
            raise InvalidProposalTransitionError("proposal is not draft")

        document = self._resolve_document(tenant_id, proposal_id, document_id)
        if document.status != "current":
            raise DocumentNotFoundError(document_id)

        deleted = self._documents.delete(tenant_id, document_id)
        if not deleted:
            raise DocumentNotFoundError(document_id)
        self._storage.delete(document.blob_key)

        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="document_deleted",
            resource_type="document",
            resource_id=document.id,
            evaluation_id=proposal.evaluation_id,
            proposal_id=proposal_id,
            metadata={"filename": document.filename, "requirement_id": document.requirement_id},
        )
