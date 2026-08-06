from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.service import AuditEventService
from procurawise.evaluations.exceptions import EvaluationNotFoundError, InvalidTransitionError
from procurawise.evaluations.models import Requirement
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.evaluations.schemas import RequirementResponse
from procurawise.reports.exceptions import RequirementsImportError
from procurawise.reports.import_schemas import (
    RequirementImportConfirmRequest,
    RequirementImportConfirmResponse,
    RequirementImportPreviewResponse,
)
from procurawise.reports.import_service import RequirementImportService
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext, require_role
from procurawise.shared.mongo import get_database
from procurawise.shared.roles import OWNER_ONLY

router = APIRouter(prefix="/evaluations/{evaluation_id}/requirements/import", tags=["reports"])

require_owner = require_role(*OWNER_ONLY)


def get_import_service(settings: Settings = Depends(get_settings)) -> RequirementImportService:
    db = get_database(settings)
    return RequirementImportService(
        evaluations=EvaluationRepository(db),
        audit=AuditEventService(AuditEventRepository(db), settings),
    )


def _requirement_response(requirement: Requirement) -> RequirementResponse:
    return RequirementResponse(
        id=requirement.id,
        dimension=requirement.dimension,
        category=requirement.category,
        title=requirement.title,
        description=requirement.description,
        priority=requirement.priority,
        response_type=requirement.response_type,
        weight=requirement.weight,
        required=requirement.required,
        buyer_guidance=requirement.buyer_guidance,
        display_order=requirement.display_order,
        options=requirement.options,
        created_at=requirement.created_at,
        updated_at=requirement.updated_at,
    )


@router.post("/preview", response_model=RequirementImportPreviewResponse)
async def preview_import(
    evaluation_id: str,
    file: Annotated[UploadFile, File()],
    settings: Settings = Depends(get_settings),
    context: ActorContext = Depends(require_owner),
    service: RequirementImportService = Depends(get_import_service),
) -> RequirementImportPreviewResponse:
    content = await file.read()
    max_bytes = settings.import_max_file_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=422, detail="file exceeds import_max_file_size_mb")
    filename = file.filename or ""
    try:
        preview = service.preview(
            context.tenant_id, evaluation_id, filename=filename, content=content
        )
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidTransitionError:
        raise HTTPException(status_code=409, detail="evaluation is not draft") from None
    except RequirementsImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return RequirementImportPreviewResponse(
        columns=preview.columns, rows=preview.rows, suggested_mapping=preview.suggested_mapping
    )


@router.post("/confirm", response_model=RequirementImportConfirmResponse, status_code=201)
def confirm_import(
    evaluation_id: str,
    body: RequirementImportConfirmRequest,
    context: ActorContext = Depends(require_owner),
    service: RequirementImportService = Depends(get_import_service),
) -> RequirementImportConfirmResponse:
    requirements = [
        Requirement.create(
            dimension=item.dimension,
            category=item.category,
            title=item.title,
            description=item.description,
            priority=item.priority,
            response_type=item.response_type,
            weight=item.weight,
            required=item.required,
            display_order=item.display_order,
            buyer_guidance=item.buyer_guidance,
            options=item.options,
        )
        for item in body.requirements
    ]
    try:
        created = service.confirm(context.tenant_id, evaluation_id, requirements, actor=context)
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidTransitionError:
        raise HTTPException(status_code=409, detail="evaluation is not draft") from None
    except RequirementsImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return RequirementImportConfirmResponse(
        requirements=[_requirement_response(r) for r in created]
    )
