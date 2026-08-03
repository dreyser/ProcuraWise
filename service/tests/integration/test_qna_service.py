from dataclasses import replace

import pytest

from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.service import AuditEventService
from procurawise.evaluations.exceptions import RequirementNotFoundError
from procurawise.evaluations.models import Evaluation, Requirement
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.repository import MembershipRepository, TenantRepository, UserRepository
from procurawise.identity.service import IdentityService
from procurawise.proposals.exceptions import ProposalNotFoundError
from procurawise.proposals.models import Proposal
from procurawise.proposals.repository import ProposalRepository
from procurawise.qna.exceptions import (
    InvalidQuestionTransitionError,
    QuestionNotFoundError,
    QuestionValidationError,
    StaleQuestionVersionError,
)
from procurawise.qna.repository import QuestionRepository
from procurawise.qna.service import QuestionService
from procurawise.shared.context import ActorContext
from procurawise.shared.mongo import get_database
from tests.conftest import unique_actor_by_role

pytestmark = pytest.mark.docker


@pytest.fixture(autouse=True)
def _clean_qna(mongo_test_db):
    yield
    mongo_test_db["qna_questions"].delete_many({})
    mongo_test_db["evaluations"].delete_many({})
    mongo_test_db["proposals"].delete_many({})
    mongo_test_db["audit_events"].delete_many({})


def _vendor_actor(mongo_test_settings, membership_id: str) -> ActorContext:
    db = get_database(mongo_test_settings)
    identity_service = IdentityService(
        tenants=TenantRepository(db), users=UserRepository(db), memberships=MembershipRepository(db)
    )
    return identity_service.resolve_actor_context(membership_id)


def _create_collecting_proposal(
    mongo_test_settings, tenant_id: str, vendor_org_id: str, *, with_requirement: bool = True
) -> tuple[str, str, str | None]:
    """Returns (evaluation_id, proposal_id, requirement_id). Bypasses the
    full approval workflow (raw status update) - this test targets
    QuestionService directly, not EvaluationService's transition machinery."""
    db = get_database(mongo_test_settings)
    evaluations = EvaluationRepository(db)
    proposals = ProposalRepository(db)

    evaluation = Evaluation.create(tenant_id, "RFP con preguntas", "", "owner-membership")
    requirement_id = None
    if with_requirement:
        requirement = Requirement.create(
            dimension="functional",
            category="Core",
            title="Soporta SSO",
            description="d",
            priority="important",
            response_type="text",
            weight=40.0,
            required=False,
            display_order=1,
        )
        evaluation = replace(evaluation, requirements=[requirement])
        requirement_id = requirement.id
    evaluation = replace(evaluation, status="collecting_responses")
    evaluations.insert(tenant_id, evaluation.to_document())

    proposal = Proposal.create(
        tenant_id=tenant_id, evaluation_id=evaluation.id, vendor_org_id=vendor_org_id
    )
    proposals.insert(tenant_id, proposal.to_document())
    return evaluation.id, proposal.id, requirement_id


def _build_service(mongo_test_settings) -> QuestionService:
    db = get_database(mongo_test_settings)
    return QuestionService(
        questions=QuestionRepository(db),
        proposals=ProposalRepository(db),
        evaluations=EvaluationRepository(db),
        audit=AuditEventService(AuditEventRepository(db), mongo_test_settings),
    )


def test_create_question_general_and_requirement_scoped(mongo_test_settings, seeded_actors) -> None:
    tenant_id, membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    actor = _vendor_actor(mongo_test_settings, membership_id)
    _evaluation_id, proposal_id, requirement_id = _create_collecting_proposal(
        mongo_test_settings, tenant_id, actor.vendor_org_id
    )
    service = _build_service(mongo_test_settings)

    general = service.create_question(
        tenant_id,
        actor.vendor_org_id,
        proposal_id,
        "general",
        None,
        "Cuando cierra el RFP?",
        actor=actor,
    )
    assert general.scope == "general"
    assert general.status == "open"

    scoped = service.create_question(
        tenant_id,
        actor.vendor_org_id,
        proposal_id,
        "requirement",
        requirement_id,
        "Que protocolo de SSO soportan?",
        actor=actor,
    )
    assert scoped.requirement_id == requirement_id

    listed = service.list_for_proposal(tenant_id, actor.vendor_org_id, proposal_id)
    assert {q.id for q in listed} == {general.id, scoped.id}


def test_create_question_rejects_foreign_requirement_id(mongo_test_settings, seeded_actors) -> None:
    tenant_id, membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    actor = _vendor_actor(mongo_test_settings, membership_id)
    _evaluation_id, proposal_id, _requirement_id = _create_collecting_proposal(
        mongo_test_settings, tenant_id, actor.vendor_org_id
    )
    service = _build_service(mongo_test_settings)

    with pytest.raises(RequirementNotFoundError):
        service.create_question(
            tenant_id,
            actor.vendor_org_id,
            proposal_id,
            "requirement",
            "does-not-exist",
            "?",
            actor=actor,
        )


def test_create_question_requires_requirement_id_for_requirement_scope(
    mongo_test_settings, seeded_actors
) -> None:
    tenant_id, membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    actor = _vendor_actor(mongo_test_settings, membership_id)
    _evaluation_id, proposal_id, _requirement_id = _create_collecting_proposal(
        mongo_test_settings, tenant_id, actor.vendor_org_id
    )
    service = _build_service(mongo_test_settings)

    with pytest.raises(QuestionValidationError):
        service.create_question(
            tenant_id, actor.vendor_org_id, proposal_id, "requirement", None, "?", actor=actor
        )


def test_create_question_rejected_when_evaluation_not_collecting_responses(
    mongo_test_settings, seeded_actors
) -> None:
    tenant_id, membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    actor = _vendor_actor(mongo_test_settings, membership_id)
    _evaluation_id, proposal_id, _requirement_id = _create_collecting_proposal(
        mongo_test_settings, tenant_id, actor.vendor_org_id
    )
    db = get_database(mongo_test_settings)
    db["evaluations"].update_one({"_id": _evaluation_id}, {"$set": {"status": "evaluating"}})
    service = _build_service(mongo_test_settings)

    with pytest.raises(InvalidQuestionTransitionError):
        service.create_question(
            tenant_id, actor.vendor_org_id, proposal_id, "general", None, "?", actor=actor
        )


def test_withdraw_only_while_open(mongo_test_settings, seeded_actors) -> None:
    tenant_id, membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    actor = _vendor_actor(mongo_test_settings, membership_id)
    _evaluation_id, proposal_id, _requirement_id = _create_collecting_proposal(
        mongo_test_settings, tenant_id, actor.vendor_org_id
    )
    service = _build_service(mongo_test_settings)
    question = service.create_question(
        tenant_id, actor.vendor_org_id, proposal_id, "general", None, "?", actor=actor
    )

    service.withdraw_question(tenant_id, actor.vendor_org_id, proposal_id, question.id, actor=actor)
    assert service.list_for_proposal(tenant_id, actor.vendor_org_id, proposal_id) == []

    with pytest.raises(QuestionNotFoundError):
        service.withdraw_question(
            tenant_id, actor.vendor_org_id, proposal_id, question.id, actor=actor
        )


def test_withdraw_rejected_once_answered(mongo_test_settings, seeded_actors) -> None:
    tenant_id, membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    actor = _vendor_actor(mongo_test_settings, membership_id)
    evaluation_id, proposal_id, _requirement_id = _create_collecting_proposal(
        mongo_test_settings, tenant_id, actor.vendor_org_id
    )
    service = _build_service(mongo_test_settings)
    question = service.create_question(
        tenant_id, actor.vendor_org_id, proposal_id, "general", None, "?", actor=actor
    )
    service.publish_answer(
        tenant_id, evaluation_id, question.id, "Yes.", "private", question.version, actor=actor
    )

    with pytest.raises(InvalidQuestionTransitionError):
        service.withdraw_question(
            tenant_id, actor.vendor_org_id, proposal_id, question.id, actor=actor
        )


def test_publish_answer_first_version_then_republish_preserves_history(
    mongo_test_settings, seeded_actors
) -> None:
    tenant_id, membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    actor = _vendor_actor(mongo_test_settings, membership_id)
    evaluation_id, proposal_id, _requirement_id = _create_collecting_proposal(
        mongo_test_settings, tenant_id, actor.vendor_org_id
    )
    service = _build_service(mongo_test_settings)
    question = service.create_question(
        tenant_id, actor.vendor_org_id, proposal_id, "general", None, "?", actor=actor
    )

    answered = service.publish_answer(
        tenant_id,
        evaluation_id,
        question.id,
        "Private answer",
        "private",
        question.version,
        actor=actor,
    )
    assert answered.status == "answered"
    assert answered.current_answer is not None
    assert answered.current_answer.version == 1
    assert answered.current_answer.visibility == "private"
    assert answered.answer_history == []

    republished = service.publish_answer(
        tenant_id,
        evaluation_id,
        question.id,
        "Published answer",
        "published_anonymized",
        answered.version,
        actor=actor,
    )
    assert republished.current_answer is not None
    assert republished.current_answer.version == 2
    assert republished.current_answer.visibility == "published_anonymized"
    assert len(republished.answer_history) == 1
    assert republished.answer_history[0].body == "Private answer"


def test_publish_answer_rejects_stale_version(mongo_test_settings, seeded_actors) -> None:
    tenant_id, membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    actor = _vendor_actor(mongo_test_settings, membership_id)
    evaluation_id, proposal_id, _requirement_id = _create_collecting_proposal(
        mongo_test_settings, tenant_id, actor.vendor_org_id
    )
    service = _build_service(mongo_test_settings)
    question = service.create_question(
        tenant_id, actor.vendor_org_id, proposal_id, "general", None, "?", actor=actor
    )

    with pytest.raises(StaleQuestionVersionError):
        service.publish_answer(
            tenant_id, evaluation_id, question.id, "A", "private", 999, actor=actor
        )


def test_list_published_for_evaluation_excludes_private_and_own(
    mongo_test_settings, seeded_actors, mongo_test_db
) -> None:
    tenant_id, membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    actor = _vendor_actor(mongo_test_settings, membership_id)
    evaluation_id, proposal_id, _requirement_id = _create_collecting_proposal(
        mongo_test_settings, tenant_id, actor.vendor_org_id
    )
    service = _build_service(mongo_test_settings)

    private_q = service.create_question(
        tenant_id, actor.vendor_org_id, proposal_id, "general", None, "private one", actor=actor
    )
    service.publish_answer(
        tenant_id, evaluation_id, private_q.id, "shh", "private", private_q.version, actor=actor
    )
    published_q = service.create_question(
        tenant_id, actor.vendor_org_id, proposal_id, "general", None, "public one", actor=actor
    )
    service.publish_answer(
        tenant_id,
        evaluation_id,
        published_q.id,
        "everyone can see this",
        "published_anonymized",
        published_q.version,
        actor=actor,
    )

    # A second vendor org linked to the same evaluation.
    other_proposal = Proposal.create(
        tenant_id=tenant_id, evaluation_id=evaluation_id, vendor_org_id="other-vendor-org"
    )
    ProposalRepository(get_database(mongo_test_settings)).insert(
        tenant_id, other_proposal.to_document()
    )

    published_for_other = service.list_published_for_evaluation(
        tenant_id, "other-vendor-org", other_proposal.id
    )
    assert {q.id for q in published_for_other} == {published_q.id}

    # The asking vendor never gets its own questions back from this
    # "peers" listing - it already sees them via list_for_proposal.
    published_for_self = service.list_published_for_evaluation(
        tenant_id, actor.vendor_org_id, proposal_id
    )
    assert published_for_self == []


def test_cross_vendor_cannot_list_or_withdraw_anothers_questions(
    mongo_test_settings, seeded_actors
) -> None:
    tenant_id, membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    actor = _vendor_actor(mongo_test_settings, membership_id)
    _evaluation_id, proposal_id, _requirement_id = _create_collecting_proposal(
        mongo_test_settings, tenant_id, actor.vendor_org_id
    )
    service = _build_service(mongo_test_settings)
    question = service.create_question(
        tenant_id, actor.vendor_org_id, proposal_id, "general", None, "?", actor=actor
    )

    with pytest.raises(ProposalNotFoundError):
        service.list_for_proposal(tenant_id, "some-other-vendor-org", proposal_id)
    with pytest.raises(ProposalNotFoundError):
        service.withdraw_question(
            tenant_id, "some-other-vendor-org", proposal_id, question.id, actor=actor
        )


def test_buyer_sees_full_question_list_with_real_identity(
    mongo_test_settings, seeded_actors
) -> None:
    tenant_id, membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    actor = _vendor_actor(mongo_test_settings, membership_id)
    evaluation_id, proposal_id, _requirement_id = _create_collecting_proposal(
        mongo_test_settings, tenant_id, actor.vendor_org_id
    )
    service = _build_service(mongo_test_settings)
    question = service.create_question(
        tenant_id, actor.vendor_org_id, proposal_id, "general", None, "?", actor=actor
    )

    buyer_view = service.list_for_evaluation_as_buyer(tenant_id, evaluation_id)
    assert len(buyer_view) == 1
    assert buyer_view[0].id == question.id
    assert buyer_view[0].vendor_org_id == actor.vendor_org_id
