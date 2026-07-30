from fastapi import APIRouter, Depends, HTTPException, Query

from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.schemas import AuditEventListResponse, AuditEventResponse
from procurawise.audit.service import AuditEventService, InvalidAuditEventCursorError
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext, require_role
from procurawise.shared.mongo import get_database

router = APIRouter(prefix="/evaluations/{evaluation_id}", tags=["audit"])

BUYER_READ_ROLES = ("evaluation_owner", "evaluator")
require_buyer_read = require_role(*BUYER_READ_ROLES)


def get_audit_event_service(settings: Settings = Depends(get_settings)) -> AuditEventService:
    db = get_database(settings)
    return AuditEventService(AuditEventRepository(db), settings)


def get_evaluation_repository(settings: Settings = Depends(get_settings)) -> EvaluationRepository:
    return EvaluationRepository(get_database(settings))


@router.get("/audit-events", response_model=AuditEventListResponse)
def list_audit_events(
    evaluation_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    context: ActorContext = Depends(require_buyer_read),
    service: AuditEventService = Depends(get_audit_event_service),
    evaluations: EvaluationRepository = Depends(get_evaluation_repository),
) -> AuditEventListResponse:
    # Same tenant-isolation shape as every other buyer route: an evaluation
    # belonging to a different tenant is a 404, not a 403 (plan §11) - never
    # confirm cross-tenant existence to the caller.
    if evaluations.find_by_id(context.tenant_id, evaluation_id) is None:
        raise HTTPException(status_code=404) from None

    try:
        events, next_cursor = service.list_for_evaluation(
            context.tenant_id, evaluation_id, limit=limit, cursor=cursor
        )
    except InvalidAuditEventCursorError:
        raise HTTPException(status_code=422, detail="invalid cursor") from None

    return AuditEventListResponse(
        items=[
            AuditEventResponse(
                id=e.id,
                occurred_at=e.occurred_at,
                actor_type=e.actor_type,
                actor_membership_id=e.actor_membership_id,
                actor_user_id=e.actor_user_id,
                actor_vendor_org_id=e.actor_vendor_org_id,
                actor_role=e.actor_role,
                action=e.action,
                resource_type=e.resource_type,
                resource_id=e.resource_id,
                evaluation_id=e.evaluation_id,
                proposal_id=e.proposal_id,
                snapshot_id=e.snapshot_id,
                version=e.version,
                outcome=e.outcome,
                correlation_id=e.correlation_id,
                metadata=e.metadata,
            )
            for e in events
        ],
        next_cursor=next_cursor,
    )
