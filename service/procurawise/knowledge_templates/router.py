from fastapi import APIRouter, Depends, HTTPException

from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.service import AuditEventService
from procurawise.evaluations.exceptions import EvaluationNotFoundError, InvalidTransitionError
from procurawise.evaluations.models import Requirement
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.evaluations.schemas import (
    RequirementCreateRequest,
    RequirementResponse,
    RequirementUpdateRequest,
)
from procurawise.knowledge_templates.exceptions import (
    KnowledgeTemplateNotFoundError,
    TemplateItemNotFoundError,
)
from procurawise.knowledge_templates.models import KnowledgeTemplate
from procurawise.knowledge_templates.repository import KnowledgeTemplateRepository
from procurawise.knowledge_templates.schemas import (
    ApplyKnowledgeTemplateRequest,
    ApplyKnowledgeTemplateResponse,
    KnowledgeTemplateCreateRequest,
    KnowledgeTemplateDetailResponse,
    KnowledgeTemplateListResponse,
    KnowledgeTemplateSummaryResponse,
    KnowledgeTemplateUpdateRequest,
)
from procurawise.knowledge_templates.service import KnowledgeTemplateService
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext, require_role
from procurawise.shared.mongo import get_database
from procurawise.shared.roles import BUYER_READ_ROLES, OWNER_ONLY

router = APIRouter(prefix="/knowledge-templates", tags=["knowledge-templates"])
apply_router = APIRouter(prefix="/evaluations/{evaluation_id}", tags=["knowledge-templates"])

require_buyer_read = require_role(*BUYER_READ_ROLES)
require_owner = require_role(*OWNER_ONLY)


def get_knowledge_template_service(
    settings: Settings = Depends(get_settings),
) -> KnowledgeTemplateService:
    db = get_database(settings)
    return KnowledgeTemplateService(
        templates=KnowledgeTemplateRepository(db),
        evaluations=EvaluationRepository(db),
        audit=AuditEventService(AuditEventRepository(db), settings),
    )


def _item_response(item: Requirement) -> RequirementResponse:
    return RequirementResponse(
        id=item.id,
        dimension=item.dimension,
        category=item.category,
        title=item.title,
        description=item.description,
        priority=item.priority,
        response_type=item.response_type,
        weight=item.weight,
        required=item.required,
        buyer_guidance=item.buyer_guidance,
        display_order=item.display_order,
        options=item.options,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _summary_response(template: KnowledgeTemplate) -> KnowledgeTemplateSummaryResponse:
    return KnowledgeTemplateSummaryResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        item_count=len(template.items),
        created_by_membership_id=template.created_by_membership_id,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


def _detail_response(template: KnowledgeTemplate) -> KnowledgeTemplateDetailResponse:
    return KnowledgeTemplateDetailResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        items=[_item_response(item) for item in template.items],
        created_by_membership_id=template.created_by_membership_id,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


@router.post("", response_model=KnowledgeTemplateDetailResponse, status_code=201)
def create_template(
    body: KnowledgeTemplateCreateRequest,
    context: ActorContext = Depends(require_owner),
    service: KnowledgeTemplateService = Depends(get_knowledge_template_service),
) -> KnowledgeTemplateDetailResponse:
    template = service.create_template(
        context.tenant_id, body.name, body.description, actor=context
    )
    return _detail_response(template)


@router.get("", response_model=KnowledgeTemplateListResponse)
def list_templates(
    context: ActorContext = Depends(require_buyer_read),
    service: KnowledgeTemplateService = Depends(get_knowledge_template_service),
) -> KnowledgeTemplateListResponse:
    templates = service.list_templates(context.tenant_id)
    return KnowledgeTemplateListResponse(items=[_summary_response(t) for t in templates])


@router.get("/{template_id}", response_model=KnowledgeTemplateDetailResponse)
def get_template(
    template_id: str,
    context: ActorContext = Depends(require_buyer_read),
    service: KnowledgeTemplateService = Depends(get_knowledge_template_service),
) -> KnowledgeTemplateDetailResponse:
    try:
        template = service.get_template(context.tenant_id, template_id)
    except KnowledgeTemplateNotFoundError:
        raise HTTPException(status_code=404) from None
    return _detail_response(template)


@router.patch("/{template_id}", response_model=KnowledgeTemplateDetailResponse)
def update_template(
    template_id: str,
    body: KnowledgeTemplateUpdateRequest,
    context: ActorContext = Depends(require_owner),
    service: KnowledgeTemplateService = Depends(get_knowledge_template_service),
) -> KnowledgeTemplateDetailResponse:
    try:
        template = service.update_template(
            context.tenant_id, template_id, body.name, body.description, actor=context
        )
    except KnowledgeTemplateNotFoundError:
        raise HTTPException(status_code=404) from None
    return _detail_response(template)


@router.delete("/{template_id}", status_code=204)
def delete_template(
    template_id: str,
    context: ActorContext = Depends(require_owner),
    service: KnowledgeTemplateService = Depends(get_knowledge_template_service),
) -> None:
    try:
        service.delete_template(context.tenant_id, template_id, actor=context)
    except KnowledgeTemplateNotFoundError:
        raise HTTPException(status_code=404) from None


@router.post("/{template_id}/items", response_model=RequirementResponse, status_code=201)
def add_item(
    template_id: str,
    body: RequirementCreateRequest,
    context: ActorContext = Depends(require_owner),
    service: KnowledgeTemplateService = Depends(get_knowledge_template_service),
) -> RequirementResponse:
    try:
        item = service.add_item(
            context.tenant_id,
            template_id,
            dimension=body.dimension,
            category=body.category,
            title=body.title,
            description=body.description,
            priority=body.priority,
            response_type=body.response_type,
            weight=body.weight,
            required=body.required,
            display_order=body.display_order,
            buyer_guidance=body.buyer_guidance,
            options=body.options,
            actor=context,
        )
    except KnowledgeTemplateNotFoundError:
        raise HTTPException(status_code=404) from None
    return _item_response(item)


@router.patch("/{template_id}/items/{item_id}", response_model=RequirementResponse)
def update_item(
    template_id: str,
    item_id: str,
    body: RequirementUpdateRequest,
    context: ActorContext = Depends(require_owner),
    service: KnowledgeTemplateService = Depends(get_knowledge_template_service),
) -> RequirementResponse:
    field_updates = body.model_dump(exclude_unset=True)
    try:
        item = service.update_item(
            context.tenant_id, template_id, item_id, field_updates, actor=context
        )
    except (KnowledgeTemplateNotFoundError, TemplateItemNotFoundError):
        raise HTTPException(status_code=404) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _item_response(item)


@router.delete("/{template_id}/items/{item_id}", status_code=204)
def delete_item(
    template_id: str,
    item_id: str,
    context: ActorContext = Depends(require_owner),
    service: KnowledgeTemplateService = Depends(get_knowledge_template_service),
) -> None:
    try:
        service.delete_item(context.tenant_id, template_id, item_id, actor=context)
    except (KnowledgeTemplateNotFoundError, TemplateItemNotFoundError):
        raise HTTPException(status_code=404) from None


@apply_router.post(
    "/apply-knowledge-template", response_model=ApplyKnowledgeTemplateResponse, status_code=201
)
def apply_knowledge_template(
    evaluation_id: str,
    body: ApplyKnowledgeTemplateRequest,
    context: ActorContext = Depends(require_owner),
    service: KnowledgeTemplateService = Depends(get_knowledge_template_service),
) -> ApplyKnowledgeTemplateResponse:
    try:
        added = service.apply_to_evaluation(
            context.tenant_id, evaluation_id, body.knowledge_template_id, actor=context
        )
    except (EvaluationNotFoundError, KnowledgeTemplateNotFoundError):
        raise HTTPException(status_code=404) from None
    except InvalidTransitionError:
        raise HTTPException(status_code=409, detail="evaluation is not draft") from None
    return ApplyKnowledgeTemplateResponse(added_requirements=[_item_response(r) for r in added])
