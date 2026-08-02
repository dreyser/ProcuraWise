import dataclasses

import pytest

from procurawise.ai.internal_knowledge_provider import InternalKnowledgeProvider
from procurawise.ai.research_provider import DiscoveryQuery
from procurawise.evaluations.models import Evaluation, Requirement
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.knowledge_templates.models import KnowledgeTemplate
from procurawise.knowledge_templates.repository import KnowledgeTemplateRepository

pytestmark = pytest.mark.docker

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"


def _requirement(dimension: str, category: str, title: str, description: str) -> Requirement:
    return Requirement.create(
        dimension=dimension,
        category=category,
        title=title,
        description=description,
        priority="important",
        response_type="text",
        weight=1.0,
        required=False,
        display_order=1,
    )


@pytest.fixture(autouse=True)
def _clean_collections(mongo_test_db):
    yield
    mongo_test_db["knowledge_templates"].drop()
    mongo_test_db["evaluations"].drop()


def test_discover_filters_by_dimension_and_ranks_by_relevance(mongo_test_db) -> None:
    templates = KnowledgeTemplateRepository(mongo_test_db)
    evaluations = EvaluationRepository(mongo_test_db)
    provider = InternalKnowledgeProvider(templates, evaluations)

    template = KnowledgeTemplate.create(TENANT_A, "ERP library", "", "membership-1")
    template = dataclasses.replace(
        template,
        items=[
            _requirement(
                "functional", "Reporting", "Real-time dashboards", "Configurable reporting engine"
            ),
            _requirement("technical", "Security", "SSO support", "SAML/OIDC single sign-on"),
        ],
    )
    templates.insert(TENANT_A, template.to_document())

    evaluation = Evaluation.create(TENANT_A, "Past ERP eval", "", "membership-1")
    evaluation = dataclasses.replace(
        evaluation,
        requirements=[
            _requirement(
                "functional", "Reporting", "Custom report builder", "Drag-and-drop reporting tool"
            )
        ],
    )
    evaluations.insert(TENANT_A, evaluation.to_document())

    result = provider.discover(
        TENANT_A, DiscoveryQuery(dimension="functional", description="we need reporting dashboards")
    )

    assert result.warnings == []
    assert len(result.snippets) == 2
    allowed_source_types = ("internal_template", "internal_evaluation")
    assert all(snippet.source_type in allowed_source_types for snippet in result.snippets)
    # The two functional-dimension snippets both mention "reporting" - the
    # technical-dimension SSO item must be excluded entirely.
    assert all("SSO" not in snippet.content for snippet in result.snippets)


def test_discover_excludes_current_evaluation(mongo_test_db) -> None:
    templates = KnowledgeTemplateRepository(mongo_test_db)
    evaluations = EvaluationRepository(mongo_test_db)
    provider = InternalKnowledgeProvider(templates, evaluations)

    evaluation = Evaluation.create(TENANT_A, "In-progress eval", "", "membership-1")
    evaluation = dataclasses.replace(
        evaluation,
        requirements=[
            _requirement("functional", "Reporting", "Existing item", "Existing description")
        ],
    )
    evaluations.insert(TENANT_A, evaluation.to_document())

    result = provider.discover(
        TENANT_A,
        DiscoveryQuery(
            dimension="functional",
            description="reporting",
            exclude_evaluation_id=evaluation.id,
        ),
    )

    assert result.snippets == []


def test_discover_never_crosses_tenants(mongo_test_db) -> None:
    templates = KnowledgeTemplateRepository(mongo_test_db)
    evaluations = EvaluationRepository(mongo_test_db)
    provider = InternalKnowledgeProvider(templates, evaluations)

    template = KnowledgeTemplate.create(TENANT_B, "Other tenant library", "", "membership-1")
    template = dataclasses.replace(
        template,
        items=[_requirement("functional", "Reporting", "Foreign item", "Should never leak")],
    )
    templates.insert(TENANT_B, template.to_document())

    result = provider.discover(
        TENANT_A, DiscoveryQuery(dimension="functional", description="reporting")
    )

    assert result.snippets == []
