import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

DocumentStatus = Literal["current", "superseded"]
# Only "clean" is ever persisted (Fase 16 planning D-E5): a file the stub
# scanner flags as infected is rejected in the request and never creates a
# Document row - kept as a Literal (not a bare constant) so a future real
# scanner can widen it without reshaping the field.
ScanStatus = Literal["clean"]

_SAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_FILENAME_LENGTH = 150


def new_id() -> str:
    return uuid4().hex


def sanitize_filename(filename: str) -> str:
    """Never trust the client-supplied filename for anything path-like - the
    blob key is always built from `document_id` (a UUID, see
    Document.blob_key), never from this value directly. This only produces a
    safe *display* name (also used as the download's Content-Disposition
    filename): strips any path separators/control characters, keeps a
    conservative charset, and caps length so a pathological filename can
    never inflate the blob key or a header unreasonably."""
    base = filename.strip().replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = _SAFE_FILENAME_CHARS.sub("_", base).strip("._") or "documento"
    return cleaned[:_MAX_FILENAME_LENGTH]


def build_blob_key(
    tenant_id: str, proposal_id: str, document_id: str, version: int, filename: str
) -> str:
    """`document_id` (a UUID, never client-controlled) and `version` are what
    make this key unique and non-predictable - `filename` here must already
    be the sanitized display name (sanitize_filename), included only for
    human-readability when browsing the container directly, never trusted
    for uniqueness or path safety on its own."""
    return f"{tenant_id}/{proposal_id}/{document_id}/v{version}/{filename}"


@dataclass(frozen=True)
class Document:
    """One uploaded file instance (Fase 16). `requirement_id` is optional
    (planning decision D1): evidence tied to a specific Requirement, or a
    general proposal-level attachment when None. Versioning is per "slot" -
    replacing evidence for the same (proposal_id, requirement_id) marks the
    previous row `status="superseded"` (never deleted, never overwrites its
    blob) and inserts a new row with `version + 1`; general attachments
    (requirement_id=None) have no forced single-slot behavior, each upload
    is independent. Immutable once the parent Proposal is submitted - see
    proposals.service, which captures the `status="current"` rows into
    ProposalSnapshot.document_ids at that moment."""

    id: str
    tenant_id: str
    evaluation_id: str
    proposal_id: str
    vendor_org_id: str
    requirement_id: str | None
    version: int
    status: DocumentStatus
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    blob_key: str
    scan_status: ScanStatus
    uploaded_by_membership_id: str
    created_at: datetime

    @staticmethod
    def create(
        *,
        tenant_id: str,
        evaluation_id: str,
        proposal_id: str,
        vendor_org_id: str,
        requirement_id: str | None,
        version: int,
        filename: str,
        content_type: str,
        size_bytes: int,
        sha256: str,
        uploaded_by_membership_id: str,
    ) -> "Document":
        document_id = new_id()
        safe_filename = sanitize_filename(filename)
        return Document(
            id=document_id,
            tenant_id=tenant_id,
            evaluation_id=evaluation_id,
            proposal_id=proposal_id,
            vendor_org_id=vendor_org_id,
            requirement_id=requirement_id,
            version=version,
            status="current",
            filename=safe_filename,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256=sha256,
            blob_key=build_blob_key(tenant_id, proposal_id, document_id, version, safe_filename),
            scan_status="clean",
            uploaded_by_membership_id=uploaded_by_membership_id,
            created_at=datetime.now(UTC),
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "tenant_id": self.tenant_id,
            "evaluation_id": self.evaluation_id,
            "proposal_id": self.proposal_id,
            "vendor_org_id": self.vendor_org_id,
            "requirement_id": self.requirement_id,
            "version": self.version,
            "status": self.status,
            "filename": self.filename,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "blob_key": self.blob_key,
            "scan_status": self.scan_status,
            "uploaded_by_membership_id": self.uploaded_by_membership_id,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "Document":
        return Document(
            id=doc["_id"],
            tenant_id=doc["tenant_id"],
            evaluation_id=doc["evaluation_id"],
            proposal_id=doc["proposal_id"],
            vendor_org_id=doc["vendor_org_id"],
            requirement_id=doc.get("requirement_id"),
            version=doc["version"],
            status=doc["status"],
            filename=doc["filename"],
            content_type=doc["content_type"],
            size_bytes=doc["size_bytes"],
            sha256=doc["sha256"],
            blob_key=doc["blob_key"],
            scan_status=doc["scan_status"],
            uploaded_by_membership_id=doc["uploaded_by_membership_id"],
            created_at=doc["created_at"],
        )
