"""Fase 23 - single composition point for `ReportService`, shared by
`reports.router` (FastAPI DI) and `worker.main` (plain function call, no
FastAPI request scope) so the two never drift out of sync with each other."""

from procurawise.ai.repository import AIExecutionRepository
from procurawise.assignments.repository import AssignmentRepository
from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.service import AuditEventService
from procurawise.decisions.repository import DecisionRepository
from procurawise.decisions.service import DecisionService
from procurawise.decisions.snapshot_repository import DecisionSnapshotRepository
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.evaluations.snapshot_repository import EvaluationSnapshotRepository
from procurawise.identity.repository import (
    MembershipRepository,
    TenantRepository,
    UserRepository,
    VendorOrganizationRepository,
)
from procurawise.identity.service import IdentityService
from procurawise.notifications.dependencies import build_notification_service
from procurawise.proposals.repository import ProposalRepository
from procurawise.qna.repository import QuestionRepository
from procurawise.reports.repository import ReportRepository
from procurawise.reports.service import ReportService
from procurawise.scoring.repository import EconomicAssessmentRepository, ScoreRepository
from procurawise.scoring.service import ScoringService
from procurawise.shared.config import Settings
from procurawise.shared.messaging import get_message_bus
from procurawise.shared.mongo import get_database
from procurawise.shared.storage import AzureBlobStorage

# Container ensure_container() is idempotent but not free - only called once
# per container per process, same pattern as documents/router.py's own
# _provisioned_containers set.
_provisioned_containers: set[str] = set()


def build_report_service(settings: Settings) -> ReportService:
    db = get_database(settings)
    audit = AuditEventService(AuditEventRepository(db), settings)
    notifications = build_notification_service(settings)
    scoring = ScoringService(
        scores=ScoreRepository(db),
        proposals=ProposalRepository(db),
        evaluations=EvaluationRepository(db),
        vendor_orgs=VendorOrganizationRepository(db),
        audit=audit,
        assignments=AssignmentRepository(db),
        ai_executions=AIExecutionRepository(db),
        economic_assessments=EconomicAssessmentRepository(db),
        notifications=notifications,
    )
    decisions = DecisionService(
        decisions=DecisionRepository(db),
        snapshots=DecisionSnapshotRepository(db),
        evaluations=EvaluationRepository(db),
        proposals=ProposalRepository(db),
        vendor_orgs=VendorOrganizationRepository(db),
        memberships=MembershipRepository(db),
        scoring=scoring,
        audit=audit,
        notifications=notifications,
    )
    identity = IdentityService(
        tenants=TenantRepository(db), users=UserRepository(db), memberships=MembershipRepository(db)
    )
    storage = AzureBlobStorage.from_settings(
        settings, container_name=settings.reports_container_name
    )
    if settings.reports_container_name not in _provisioned_containers:
        storage.ensure_container()
        _provisioned_containers.add(settings.reports_container_name)
    return ReportService(
        reports=ReportRepository(db),
        evaluations=EvaluationRepository(db),
        evaluation_snapshots=EvaluationSnapshotRepository(db),
        proposals=ProposalRepository(db),
        vendor_orgs=VendorOrganizationRepository(db),
        scoring=scoring,
        decisions=decisions,
        qna=QuestionRepository(db),
        storage=storage,
        message_bus=get_message_bus(settings),
        audit=audit,
        identity=identity,
        retention_days=settings.reports_retention_days,
        download_url_ttl_minutes=settings.reports_download_url_ttl_minutes,
    )
