from typing import Any

from procurawise.audit.service import AuditEventService
from procurawise.evaluations.exceptions import EvaluationNotFoundError, InvalidTransitionError
from procurawise.evaluations.models import Evaluation, Requirement, validate_requirement_patch
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.knowledge_templates.exceptions import (
    KnowledgeTemplateNotFoundError,
    TemplateItemNotFoundError,
)
from procurawise.knowledge_templates.models import KnowledgeTemplate
from procurawise.knowledge_templates.repository import KnowledgeTemplateRepository
from procurawise.shared.context import ActorContext


class KnowledgeTemplateService:
    """Fase 11: composes directly against EvaluationRepository/Evaluation/
    Requirement (evaluations.models) rather than through EvaluationService -
    same cross-module precedent AssignmentService already established
    (Fase 9)."""

    def __init__(
        self,
        templates: KnowledgeTemplateRepository,
        evaluations: EvaluationRepository,
        audit: AuditEventService,
    ) -> None:
        self._templates = templates
        self._evaluations = evaluations
        self._audit = audit

    def _template_or_raise(self, tenant_id: str, template_id: str) -> KnowledgeTemplate:
        doc = self._templates.find_by_id(tenant_id, template_id)
        if doc is None:
            raise KnowledgeTemplateNotFoundError(template_id)
        return KnowledgeTemplate.from_document(doc)

    def create_template(
        self, tenant_id: str, name: str, description: str, *, actor: ActorContext
    ) -> KnowledgeTemplate:
        template = KnowledgeTemplate.create(
            tenant_id=tenant_id,
            name=name,
            description=description,
            created_by_membership_id=actor.membership_id,
        )
        self._templates.insert(tenant_id, template.to_document())
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="knowledge_template_created",
            resource_type="knowledge_template",
            resource_id=template.id,
            metadata={"name": name},
        )
        return template

    def get_template(self, tenant_id: str, template_id: str) -> KnowledgeTemplate:
        return self._template_or_raise(tenant_id, template_id)

    def list_templates(self, tenant_id: str) -> list[KnowledgeTemplate]:
        return [
            KnowledgeTemplate.from_document(doc) for doc in self._templates.find_many(tenant_id)
        ]

    def update_template(
        self,
        tenant_id: str,
        template_id: str,
        name: str | None,
        description: str | None,
        *,
        actor: ActorContext,
    ) -> KnowledgeTemplate:
        self._template_or_raise(tenant_id, template_id)
        updates: dict[str, Any] = {}
        if name is not None:
            updates["name"] = name
        if description is not None:
            updates["description"] = description
        fields_changed = sorted(updates.keys())
        matched = self._templates.update_metadata(tenant_id, template_id, updates)
        if not matched:
            raise KnowledgeTemplateNotFoundError(template_id)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="knowledge_template_updated",
            resource_type="knowledge_template",
            resource_id=template_id,
            metadata={"fields_changed": fields_changed},
        )
        return self._template_or_raise(tenant_id, template_id)

    def delete_template(self, tenant_id: str, template_id: str, *, actor: ActorContext) -> None:
        template = self._template_or_raise(tenant_id, template_id)
        deleted = self._templates.delete(tenant_id, template_id)
        if not deleted:
            raise KnowledgeTemplateNotFoundError(template_id)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="knowledge_template_deleted",
            resource_type="knowledge_template",
            resource_id=template_id,
            metadata={"name": template.name},
        )

    def add_item(
        self,
        tenant_id: str,
        template_id: str,
        *,
        dimension: str,
        category: str,
        title: str,
        description: str,
        priority: str,
        response_type: str,
        weight: float,
        required: bool,
        display_order: int,
        buyer_guidance: str | None,
        options: list[str] | None,
        actor: ActorContext,
    ) -> Requirement:
        self._template_or_raise(tenant_id, template_id)
        item = Requirement.create(
            dimension=dimension,  # type: ignore[arg-type]
            category=category,
            title=title,
            description=description,
            priority=priority,  # type: ignore[arg-type]
            response_type=response_type,  # type: ignore[arg-type]
            weight=weight,
            required=required,
            display_order=display_order,
            buyer_guidance=buyer_guidance,
            options=options,
        )
        matched = self._templates.push_item(tenant_id, template_id, item.to_document())
        if not matched:
            raise KnowledgeTemplateNotFoundError(template_id)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="knowledge_template_item_added",
            resource_type="knowledge_template",
            resource_id=template_id,
            metadata={"item_id": item.id},
        )
        return item

    def update_item(
        self,
        tenant_id: str,
        template_id: str,
        item_id: str,
        field_updates: dict[str, Any],
        *,
        actor: ActorContext,
    ) -> Requirement:
        template = self._template_or_raise(tenant_id, template_id)
        current = next((item for item in template.items if item.id == item_id), None)
        if current is None:
            raise TemplateItemNotFoundError(item_id)

        validate_requirement_patch(current, field_updates)

        matched = self._templates.update_item(tenant_id, template_id, item_id, field_updates)
        if not matched:
            raise TemplateItemNotFoundError(item_id)

        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="knowledge_template_item_updated",
            resource_type="knowledge_template",
            resource_id=template_id,
            metadata={"item_id": item_id, "fields_changed": sorted(field_updates.keys())},
        )
        updated_template = self._template_or_raise(tenant_id, template_id)
        for item in updated_template.items:
            if item.id == item_id:
                return item
        raise TemplateItemNotFoundError(item_id)

    def delete_item(
        self, tenant_id: str, template_id: str, item_id: str, *, actor: ActorContext
    ) -> None:
        template = self._template_or_raise(tenant_id, template_id)
        if not any(item.id == item_id for item in template.items):
            raise TemplateItemNotFoundError(item_id)
        self._templates.delete_item(tenant_id, template_id, item_id)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="knowledge_template_item_removed",
            resource_type="knowledge_template",
            resource_id=template_id,
            metadata={"item_id": item_id},
        )

    def apply_to_evaluation(
        self, tenant_id: str, evaluation_id: str, knowledge_template_id: str, *, actor: ActorContext
    ) -> list[Requirement]:
        """Applies every item on the template (founder decision: apply-all
        only, no subset selection) to a draft Evaluation in one atomic
        bulk write - not N sequential add_requirement calls, so there is no
        partial-application risk and exactly one audit event is recorded."""
        evaluation_doc = self._evaluations.find_by_id(tenant_id, evaluation_id)
        if evaluation_doc is None:
            raise EvaluationNotFoundError(evaluation_id)
        evaluation = Evaluation.from_document(evaluation_doc)
        if evaluation.status != "draft":
            raise InvalidTransitionError(evaluation_id)

        template = self._template_or_raise(tenant_id, knowledge_template_id)

        next_display_order = len(evaluation.requirements) + 1
        new_requirements: list[Requirement] = []
        for offset, item in enumerate(template.items):
            new_requirements.append(
                Requirement.create(
                    dimension=item.dimension,
                    category=item.category,
                    title=item.title,
                    description=item.description,
                    priority=item.priority,
                    response_type=item.response_type,
                    weight=item.weight,
                    required=item.required,
                    display_order=next_display_order + offset,
                    buyer_guidance=item.buyer_guidance,
                    options=item.options,
                )
            )

        if new_requirements:
            matched = self._evaluations.add_requirements_bulk(
                tenant_id,
                evaluation_id,
                [r.to_document() for r in new_requirements],
                evaluation.approval_invalidation_extra_set(),
            )
            if not matched:
                # draft status was already confirmed above; only a
                # concurrent transition away from draft between that read
                # and this write can still land here.
                raise InvalidTransitionError(evaluation_id)

        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="requirements_applied_from_template",
            resource_type="evaluation",
            resource_id=evaluation_id,
            evaluation_id=evaluation_id,
            metadata={
                "knowledge_template_id": knowledge_template_id,
                "knowledge_template_name": template.name,
                "requirement_ids": [r.id for r in new_requirements],
                "count": len(new_requirements),
            },
        )
        return new_requirements
