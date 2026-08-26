from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

from procurawise.shared.context import ActorContext

AuditActorType = Literal["buyer", "vendor_contact", "platform_admin"]

AuditResourceType = Literal[
    "evaluation",
    "requirement",
    "proposal",
    "score",
    "assignment",
    "knowledge_template",
    "ai_execution",
    "vendor_organization",
    "document",
    "qna_question",
    "economic_assessment",
    "decision",
    "report",
    "notification",
    "purchase",
    "company_profile",
]

# Stable, closed taxonomy (plan §7) - never a free-form string built ad hoc at
# the call site. PROPOSAL_ANSWER_UPDATED (autosave) is deliberately absent:
# founder decision §18.2, only the terminal PROPOSAL_SUBMITTED is audited.
AuditAction = Literal[
    "evaluation_created",
    "evaluation_updated",
    "requirement_added",
    "requirement_updated",
    "requirement_deleted",
    "vendor_linked",
    "vendor_unlinked",
    "evaluation_collection_started",
    "evaluation_scoring_started",
    "evaluation_completed",
    "proposal_submitted",
    "score_created",
    "score_updated",
    "assignment_created",
    "assignment_removed",
    "platform_admin_cross_tenant_read",
    # Fase 12 (plan §27) - gate the existing evaluation_collection_started
    # transition with an internal approval step, plus the immutable
    # publication snapshot. evaluation_collection_started is unchanged/
    # unremoved; evaluation_published is emitted alongside it at publish time.
    "evaluation_approver_set",
    "evaluation_approval_requested",
    "evaluation_approval_withdrawn",
    "evaluation_approved",
    "evaluation_rejected",
    "evaluation_published",
    # Fase 11 (biblioteca de requerimientos, sin IA) - resource_type
    # "knowledge_template" for template/item CRUD; "requirements_applied_
    # from_template" reuses resource_type "evaluation" (same pattern
    # vendor_linked already follows) since it mutates the target Evaluation.
    "knowledge_template_created",
    "knowledge_template_updated",
    "knowledge_template_deleted",
    "knowledge_template_item_added",
    "knowledge_template_item_updated",
    "knowledge_template_item_removed",
    "requirements_applied_from_template",
    # Fase 13 (ai, ADR 0021) - resource_type "ai_execution" for the job
    # lifecycle events; "ai_requirements_accepted" reuses resource_type
    # "ai_execution" too (not "evaluation"/"requirement") since it records
    # which AIExecution's candidates were accepted, same reasoning as
    # requirements_applied_from_template pointing at its own resource.
    "ai_generation_requested",
    "ai_generation_succeeded",
    "ai_generation_failed",
    "ai_requirements_accepted",
    # Fase 15 (NDA/COI reales + auth productiva de proveedor +
    # colaboradores multiples) - resource_type "vendor_organization" for the
    # whole family, including "agreement_accepted" (the acceptance itself
    # lives in its own append-only agreements collection, but the event that
    # a given user cleared the gate is still audit-trail-worthy the same way
    # every other business mutation is).
    "vendor_organization_created",
    "vendor_collaborator_invited",
    "vendor_invitation_revoked",
    "vendor_invitation_accepted",
    "agreement_accepted",
    # Fase 16 (documents: carga, escaneo AV stub, versionado, URLs
    # temporales) - resource_type "document". document_upload_rejected is
    # emitted for a scan/validation rejection without ever creating the
    # Document row it would have described.
    "document_uploaded",
    "document_replaced",
    "document_deleted",
    "document_upload_rejected",
    "document_download_url_issued",
    # Fase 17 (qna: preguntas ligadas/generales, publicación anonimizada/
    # privada) - resource_type "qna_question". qna_answer_published covers
    # both the first answer and any later republication/visibility change
    # to the same Question - metadata.version/metadata.visibility
    # distinguish the case, no need to multiply actions per combination.
    "qna_question_created",
    "qna_question_withdrawn",
    "qna_answer_published",
    # Fase 18 (evaluacion asistida por IA, ADR 0022) - resource_type
    # "ai_execution", same as the Fase 13 ai_generation_* family. Accepting
    # or modifying a suggestion is NOT a new action: it's an ordinary
    # score_created/score_updated (above), with metadata.ai_decision
    # ("accepted"|"modified") added when the write references a
    # source_ai_execution_id - never a separate audited action, since it's
    # never a separate write path either (plan §1/§11).
    "ai_score_suggestion_requested",
    "ai_score_suggestion_succeeded",
    "ai_score_suggestion_failed",
    # Fase 20 (scoring económico completo, ADR 0009) - resource_type
    # "economic_assessment" for the commercial/risk rubric writes (the
    # automatic TCO-normalized component is calculated in vivo, never
    # written, so it never produces an audit event of its own).
    "economic_assessment_created",
    "economic_assessment_updated",
    # Fase 21 (ADR 0013, FR-047) - resource_type "proposal" (already exists,
    # reused - same pattern as vendor_linked/proposal_submitted). No
    # separate action for the round closing (start-evaluation) or for an
    # individual answer/cost-item flipping inherited->modified/removed -
    # those reuse evaluation_scoring_started and stay unaudited
    # respectively, exactly like every ordinary draft edit already is.
    "proposal_reopened",
    # Fase 22 (plan Bloqueante #1, Opcion B) - resource_type "decision". This
    # approval act is independent from evaluation_approver_set/_requested/
    # _withdrawn/_approved/_rejected above (Fase 12, publication) - Decision
    # carries its own approver_membership_id, never
    # Evaluation.approver_membership_id, so the two families of actions are
    # deliberately never conflated even though their names/shapes mirror
    # each other.
    "decision_created",
    "decision_updated",
    "decision_approver_set",
    "decision_approval_requested",
    "decision_approval_withdrawn",
    "decision_approved",
    "decision_rejected",
    # Fase 23 (reports, ADR 0023) - resource_type "report". No
    # report_generation_running action (mirrors AIExecution: only the
    # terminal/requested transitions are audit-worthy, not the
    # queued->running step, same as ai_generation_* never audits a
    # "started" event either).
    "report_generation_requested",
    "report_generation_succeeded",
    "report_generation_failed",
    "report_downloaded",
    # resource_type "evaluation" (reused, same pattern as
    # requirements_applied_from_template, Fase 11 - it mutates the target
    # Evaluation's requirements, not a resource of its own).
    "requirements_import_confirmed",
    # Fase 24 (notifications, ADR 0024) - resource_type "notification". Only
    # the delivery *mechanism's* own lifecycle is audited here, not the
    # in-app Notification row's mere creation - that row is always derivative
    # of an already-audited action (evaluation_published, proposal_submitted,
    # etc.), so auditing its creation too would just double every existing
    # audited action. notification_email_delivery_failed fires on a single
    # failed attempt that will still retry; notification_email_delivery_
    # exhausted is the terminal state once notification_email_max_attempts
    # is reached.
    "notification_email_delivery_succeeded",
    "notification_email_delivery_failed",
    "notification_email_delivery_exhausted",
    # Fase 25 (billing/admin, ADR 0025) - resource_type "purchase". The
    # platform_admin cross-tenant billing read (admin/service.py) reuses the
    # existing platform_admin_cross_tenant_read action (Fase 9) rather than
    # adding a billing-specific twin - that action is resource-agnostic by
    # design, and resource_type="purchase" already distinguishes it. No
    # action exists for a rejected webhook signature: an unauthenticated,
    # tenant-less request has neither a tenant_id nor an ActorContext, the
    # two things AuditEvent.create() structurally requires - that case is
    # structured-logged (billing/service.py), not audited.
    "billing_checkout_session_created",
    "billing_payment_succeeded",
    "billing_checkout_expired",
    # ADR 0026 (R2, UAT-06/07/08) - resource_type "evaluation" (reused, same
    # pattern as the approval family above). "_changes_requested" variants
    # are never the same action as their "_rejected" sibling even though
    # both persist review_status/approval_status="rejected" - the action
    # itself is the audit-trail discriminator the founder's blocking
    # decision (2026-08-24) required, not an optional metadata flag a reader
    # could ignore.
    "evaluation_reviewer_set",
    "evaluation_review_requested",
    "evaluation_review_withdrawn",
    "evaluation_review_approved",
    "evaluation_review_rejected",
    "evaluation_review_changes_requested",
    "evaluation_changes_requested",
    # UAT-03 (R4) - resource_type "company_profile" (id == tenant_id, same
    # 1:1 grain as billing.BillingAccount). No "_created" action: the row's
    # lazy first materialization is always empty (CompanyProfile.create()),
    # never audit-worthy on its own - only an actual field change is.
    "company_profile_updated",
]


def new_id() -> str:
    return uuid4().hex


def _actor_type_for_role(role: str) -> AuditActorType:
    if role == "vendor_contact":
        return "vendor_contact"
    if role == "platform_admin":
        return "platform_admin"
    return "buyer"


@dataclass(frozen=True)
class AuditEvent:
    """Append-only record of a relevant business mutation (plan §7). Never
    constructed directly by a router from client input - `tenant_id`,
    `actor_*`, `occurred_at` and `action` are always server-derived (from the
    resolved ActorContext and the instrumentation call site), never accepted
    from a request body. `metadata` is an explicit per-action allowlist built
    by the caller, never a raw diff or a passthrough of a request body - see
    audit.service and CLAUDE.md's sensitive-data rules."""

    id: str
    tenant_id: str
    occurred_at: datetime
    actor_type: AuditActorType
    actor_membership_id: str
    actor_user_id: str | None
    actor_vendor_org_id: str | None
    actor_role: str
    action: AuditAction
    resource_type: AuditResourceType
    resource_id: str
    evaluation_id: str | None
    proposal_id: str | None
    snapshot_id: str | None
    version: int | None
    outcome: Literal["success"]
    correlation_id: str | None
    metadata: dict[str, Any]
    expires_at: datetime

    @staticmethod
    def create(
        *,
        tenant_id: str,
        actor: ActorContext,
        action: AuditAction,
        resource_type: AuditResourceType,
        resource_id: str,
        evaluation_id: str | None = None,
        proposal_id: str | None = None,
        snapshot_id: str | None = None,
        version: int | None = None,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        retention_days: int,
    ) -> "AuditEvent":
        now = datetime.now(UTC)
        return AuditEvent(
            id=new_id(),
            tenant_id=tenant_id,
            occurred_at=now,
            actor_type=_actor_type_for_role(actor.role),
            actor_membership_id=actor.membership_id,
            actor_user_id=actor.user_id,
            actor_vendor_org_id=actor.vendor_org_id,
            actor_role=actor.role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            evaluation_id=evaluation_id,
            proposal_id=proposal_id,
            snapshot_id=snapshot_id,
            version=version,
            outcome="success",
            correlation_id=correlation_id,
            metadata=metadata or {},
            expires_at=now + timedelta(days=retention_days),
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "tenant_id": self.tenant_id,
            "occurred_at": self.occurred_at,
            "actor_type": self.actor_type,
            "actor_membership_id": self.actor_membership_id,
            "actor_user_id": self.actor_user_id,
            "actor_vendor_org_id": self.actor_vendor_org_id,
            "actor_role": self.actor_role,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "evaluation_id": self.evaluation_id,
            "proposal_id": self.proposal_id,
            "snapshot_id": self.snapshot_id,
            "version": self.version,
            "outcome": self.outcome,
            "correlation_id": self.correlation_id,
            "metadata": self.metadata,
            "expires_at": self.expires_at,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "AuditEvent":
        return AuditEvent(
            id=doc["_id"],
            tenant_id=doc["tenant_id"],
            occurred_at=doc["occurred_at"],
            actor_type=doc["actor_type"],
            actor_membership_id=doc["actor_membership_id"],
            actor_user_id=doc.get("actor_user_id"),
            actor_vendor_org_id=doc.get("actor_vendor_org_id"),
            actor_role=doc["actor_role"],
            action=doc["action"],
            resource_type=doc["resource_type"],
            resource_id=doc["resource_id"],
            evaluation_id=doc.get("evaluation_id"),
            proposal_id=doc.get("proposal_id"),
            snapshot_id=doc.get("snapshot_id"),
            version=doc.get("version"),
            outcome=doc["outcome"],
            correlation_id=doc.get("correlation_id"),
            metadata=doc.get("metadata", {}),
            expires_at=doc["expires_at"],
        )
