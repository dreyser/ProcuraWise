from dataclasses import replace

from procurawise.evaluations.models import Requirement
from procurawise.knowledge_templates.models import KnowledgeTemplate


def test_knowledge_template_create_defaults_to_empty_items() -> None:
    template = KnowledgeTemplate.create(
        tenant_id="t", name="Plantilla estándar", description="", created_by_membership_id="m"
    )
    assert template.items == []
    assert template.tenant_id == "t"
    assert template.name == "Plantilla estándar"


def test_knowledge_template_round_trips_through_document_with_items() -> None:
    item = Requirement.create(
        dimension="functional",
        category="c",
        title="t",
        description="d",
        priority="desirable",
        response_type="text",
        weight=5.0,
        required=False,
        display_order=1,
    )
    template = KnowledgeTemplate.create(
        tenant_id="t", name="Plantilla", description="d", created_by_membership_id="m"
    )
    template = replace(template, items=[item])
    restored = KnowledgeTemplate.from_document(template.to_document())
    assert restored == template


def test_knowledge_template_round_trips_through_document_with_no_items() -> None:
    template = KnowledgeTemplate.create(
        tenant_id="t", name="Plantilla vacía", description="", created_by_membership_id="m"
    )
    restored = KnowledgeTemplate.from_document(template.to_document())
    assert restored == template
