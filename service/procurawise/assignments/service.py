from pymongo.errors import DuplicateKeyError

from procurawise.assignments.exceptions import (
    AssignmentNotFoundError,
    AssignmentUpdateNotPermittedError,
    DuplicateAssignmentError,
    EvaluatorMembershipNotFoundError,
    EvaluatorRoleMismatchError,
    SectionNotFoundError,
)
from procurawise.assignments.models import Assignment, AssignmentStatus
from procurawise.assignments.repository import AssignmentRepository
from procurawise.audit.service import AuditEventService
from procurawise.evaluations.exceptions import EvaluationNotFoundError
from procurawise.evaluations.models import Dimension, Evaluation
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.repository import MembershipRepository
from procurawise.shared.context import ActorContext
from procurawise.shared.roles import EVALUATOR_ROLE_BY_DIMENSION


class AssignmentService:
    def __init__(
        self,
        assignments: AssignmentRepository,
        evaluations: EvaluationRepository,
        memberships: MembershipRepository,
        audit: AuditEventService,
    ) -> None:
        self._assignments = assignments
        self._evaluations = evaluations
        self._memberships = memberships
        self._audit = audit

    def _evaluation_or_raise(self, tenant_id: str, evaluation_id: str) -> Evaluation:
        doc = self._evaluations.find_by_id(tenant_id, evaluation_id)
        if doc is None:
            raise EvaluationNotFoundError(evaluation_id)
        return Evaluation.from_document(doc)

    def create_assignment(
        self,
        tenant_id: str,
        evaluation_id: str,
        dimension: Dimension,
        section: str,
        evaluator_membership_id: str,
        *,
        actor: ActorContext,
    ) -> Assignment:
        evaluation = self._evaluation_or_raise(tenant_id, evaluation_id)

        section_exists = any(
            r.dimension == dimension and r.category == section for r in evaluation.requirements
        )
        if not section_exists:
            raise SectionNotFoundError(section)

        membership_doc = self._memberships.find_by_id_and_tenant(evaluator_membership_id, tenant_id)
        if membership_doc is None:
            raise EvaluatorMembershipNotFoundError(evaluator_membership_id)
        expected_role = EVALUATOR_ROLE_BY_DIMENSION[dimension]
        if membership_doc["role"] != expected_role:
            raise EvaluatorRoleMismatchError(membership_doc["role"])

        if (
            self._assignments.find_by_natural_key(
                tenant_id, evaluation_id, dimension, section, evaluator_membership_id
            )
            is not None
        ):
            raise DuplicateAssignmentError(evaluator_membership_id)

        assignment = Assignment.create(
            tenant_id=tenant_id,
            evaluation_id=evaluation_id,
            dimension=dimension,
            section=section,
            evaluator_membership_id=evaluator_membership_id,
            assigned_by_membership_id=actor.membership_id,
        )
        try:
            self._assignments.insert(tenant_id, assignment.to_document())
        except DuplicateKeyError:
            raise DuplicateAssignmentError(evaluator_membership_id) from None

        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="assignment_created",
            resource_type="assignment",
            resource_id=assignment.id,
            evaluation_id=evaluation_id,
            metadata={
                "dimension": dimension,
                "section": section,
                "evaluator_membership_id": evaluator_membership_id,
            },
        )
        return assignment

    def list_for_evaluation(self, tenant_id: str, evaluation_id: str) -> list[Assignment]:
        self._evaluation_or_raise(tenant_id, evaluation_id)
        return [
            Assignment.from_document(doc)
            for doc in self._assignments.list_for_evaluation(tenant_id, evaluation_id)
        ]

    def update_status(
        self,
        tenant_id: str,
        evaluation_id: str,
        assignment_id: str,
        status: AssignmentStatus,
        *,
        actor: ActorContext,
    ) -> Assignment:
        doc = self._assignments.find_by_id(tenant_id, assignment_id)
        if doc is None or doc["evaluation_id"] != evaluation_id:
            raise AssignmentNotFoundError(assignment_id)
        assignment = Assignment.from_document(doc)
        is_owner = actor.role == "evaluation_owner"
        is_assigned_evaluator = actor.membership_id == assignment.evaluator_membership_id
        if not (is_owner or is_assigned_evaluator):
            raise AssignmentUpdateNotPermittedError(assignment_id)

        matched = self._assignments.update_status(tenant_id, assignment_id, status)
        if not matched:
            raise AssignmentNotFoundError(assignment_id)
        updated_doc = self._assignments.find_by_id(tenant_id, assignment_id)
        assert updated_doc is not None
        return Assignment.from_document(updated_doc)

    def delete_assignment(
        self, tenant_id: str, evaluation_id: str, assignment_id: str, *, actor: ActorContext
    ) -> None:
        doc = self._assignments.find_by_id(tenant_id, assignment_id)
        if doc is None or doc["evaluation_id"] != evaluation_id:
            raise AssignmentNotFoundError(assignment_id)
        assignment = Assignment.from_document(doc)

        deleted = self._assignments.delete(tenant_id, assignment_id)
        if not deleted:
            raise AssignmentNotFoundError(assignment_id)

        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="assignment_removed",
            resource_type="assignment",
            resource_id=assignment_id,
            evaluation_id=evaluation_id,
            metadata={
                "dimension": assignment.dimension,
                "section": assignment.section,
                "evaluator_membership_id": assignment.evaluator_membership_id,
            },
        )
