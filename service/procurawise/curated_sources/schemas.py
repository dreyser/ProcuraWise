from datetime import datetime

from procurawise.shared.api_models import APIModel


class CuratedSourceResponse(APIModel):
    id: str
    title: str
    url: str
    summary: str
    tags: list[str]
    active: bool
    created_at: datetime
    updated_at: datetime


class CuratedSourceListResponse(APIModel):
    items: list[CuratedSourceResponse]


class CreateCuratedSourceRequest(APIModel):
    title: str
    url: str
    summary: str
    tags: list[str] = []


class UpdateCuratedSourceRequest(APIModel):
    title: str | None = None
    url: str | None = None
    summary: str | None = None
    tags: list[str] | None = None
