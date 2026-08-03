from datetime import datetime

from procurawise.documents.models import DocumentStatus
from procurawise.shared.api_models import APIModel


class DocumentResponse(APIModel):
    id: str
    proposal_id: str
    requirement_id: str | None
    version: int
    status: DocumentStatus
    filename: str
    content_type: str
    size_bytes: int
    uploaded_by_membership_id: str
    created_at: datetime


class DocumentListResponse(APIModel):
    items: list[DocumentResponse]


class DocumentDownloadUrlResponse(APIModel):
    url: str
    expires_at: datetime
