from datetime import datetime

from procurawise.evaluations.schemas import RequirementResponse
from procurawise.shared.api_models import APIModel


class KnowledgeTemplateCreateRequest(APIModel):
    name: str
    description: str = ""


class KnowledgeTemplateUpdateRequest(APIModel):
    name: str | None = None
    description: str | None = None


class KnowledgeTemplateSummaryResponse(APIModel):
    id: str
    name: str
    description: str
    item_count: int
    created_by_membership_id: str
    created_at: datetime
    updated_at: datetime


class KnowledgeTemplateListResponse(APIModel):
    items: list[KnowledgeTemplateSummaryResponse]


class KnowledgeTemplateDetailResponse(APIModel):
    id: str
    name: str
    description: str
    items: list[RequirementResponse]
    created_by_membership_id: str
    created_at: datetime
    updated_at: datetime


class ApplyKnowledgeTemplateRequest(APIModel):
    knowledge_template_id: str


class ApplyKnowledgeTemplateResponse(APIModel):
    added_requirements: list[RequirementResponse]
