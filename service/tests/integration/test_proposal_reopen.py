"""Fase 21 acceptance criterion (backlog.md fila 21): "Modificar una
respuesta invalida su score; TCO nunca mezcla costos entre versiones; toda
reapertura queda auditada con justificacion." This file proves the
reopen()/herencia/max-rounds mechanics directly against the real API."""

import pytest

from procurawise.agreements.repository import AgreementRepository
from procurawise.agreements.service import AgreementService
from procurawise.identity.dev_provider import DEV_ACTOR_HEADER
from procurawise.identity.models import Membership, User, VendorOrganization
from procurawise.identity.repository import (
    MembershipRepository,
    UserRepository,
    VendorOrganizationRepository,
)
from tests.conftest import (
    approve_and_publish,
    bearer_headers_for,
    unique_actor_by_role,
    vendor_bearer_headers_for,
)

pytestmark = pytest.mark.docker


def _create_second_vendor(mongo_test_db, tenant_id: str) -> tuple[str, str]:
    """Mirrors tests/security/test_vendor_isolation.py's
    _create_second_vendor_contact - dev_seed only ever seeds one
    VendorOrganization per tenant, and this file needs a genuinely second
    one to prove a non-reopened proposal is left untouched. Returns
    (vendor_org_id, membership_id)."""
    users = UserRepository(mongo_test_db)
    vendor_orgs = VendorOrganizationRepository(mongo_test_db)
    memberships = MembershipRepository(mongo_test_db)

    user = User.create(display_name="Vendor Contact B", email="vendor.b.reopen@dev.local")
    users.insert(user.to_document())
    vendor_org = VendorOrganization.create(tenant_id=tenant_id, name="Proveedor Dos (reopen)")
    vendor_orgs.insert(tenant_id, vendor_org.to_document())
    membership = Membership.create(
        tenant_id=tenant_id, user_id=user.id, role="vendor_contact", vendor_org_id=vendor_org.id
    )
    memberships.insert(membership.to_document())

    agreements = AgreementService(AgreementRepository(mongo_test_db))
    for agreement_type in ("nda", "conflict_of_interest"):
        agreements.accept(
            tenant_id, user.id, membership.id, agreement_type, ip="127.0.0.1", user_agent="test"
        )
    return vendor_org.id, membership.id


def _setup_submitted_proposal(client, seeded_actors, mongo_test_settings, *, with_cost_item=True):
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    vendor_dev_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_dev_headers).json()["vendor_org_id"]
    vendor_headers = vendor_bearer_headers_for(vendor_membership_id, mongo_test_settings)

    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Negotiation RFP", "description": ""},
        headers=owner_headers,
    ).json()["id"]
    functional_id = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "functional",
            "category": "Core",
            "title": "Req funcional",
            "description": "d",
            "priority": "important",
            "response_type": "text",
            "weight": 40.0,
            "required": False,
            "display_order": 1,
        },
        headers=owner_headers,
    ).json()["id"]
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "technical",
            "category": "Core",
            "title": "Req tecnico",
            "description": "d",
            "priority": "important",
            "response_type": "text",
            "weight": 20.0,
            "required": False,
            "display_order": 2,
        },
        headers=owner_headers,
    )
    proposal_id = client.post(
        f"/api/v1/evaluations/{evaluation_id}/vendors",
        json={"vendor_org_id": vendor_org_id},
        headers=owner_headers,
    ).json()["id"]
    approver_membership_id = seeded_actors[(tenant_a, "approver")]
    approver_headers = bearer_headers_for(approver_membership_id, mongo_test_settings)
    approve_and_publish(
        client, owner_headers, approver_membership_id, approver_headers, evaluation_id
    )

    client.put(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/answers/{functional_id}",
        json={"value": "Respuesta inicial.", "expected_version": 1},
        headers=vendor_headers,
    )
    version = 2
    if with_cost_item:
        cost_item = client.post(
            f"/api/v1/vendor-portal/proposals/{proposal_id}/cost-items",
            json={
                "concept": "Licencia anual",
                "category": "recurring",
                "billing_unit": "usuario",
                "quantity": "10",
                "unit_price": "100",
                "currency": "MXN",
                "frequency_per_year": "1",
                "year_start": 1,
                "year_end": 1,
                "cost_type": "recurring",
                "expected_version": version,
            },
            headers=vendor_headers,
        )
        version = cost_item.json()["version"]

    client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/submit",
        json={"expected_version": version},
        headers=vendor_headers,
    )
    client.post(f"/api/v1/evaluations/{evaluation_id}/start-evaluation", headers=owner_headers)
    return {
        "tenant_id": tenant_a,
        "evaluation_id": evaluation_id,
        "proposal_id": proposal_id,
        "functional_id": functional_id,
        "owner_headers": owner_headers,
        "vendor_headers": vendor_headers,
        "vendor_org_id": vendor_org_id,
    }


def _reopen(client, ctx, *, reason="Negociacion de precio", deadline="2030-06-01T00:00:00Z"):
    return client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/proposals/{ctx['proposal_id']}/reopen",
        json={"reason": reason, "response_deadline": deadline},
        headers=ctx["owner_headers"],
    )


def test_owner_reopens_and_answers_cost_items_are_marked_inherited(
    client, seeded_actors, mongo_test_settings
) -> None:
    ctx = _setup_submitted_proposal(client, seeded_actors, mongo_test_settings)

    response = _reopen(client, ctx)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "draft"
    assert body["round"] == 1
    assert body["reopened_reason"] == "Negociacion de precio"
    assert body["reopened_at"] is not None
    for answer in body["answers"]:
        assert answer["status"] == "inherited"
        assert answer["source_proposal_version"] == 0

    evaluation = client.get(
        f"/api/v1/evaluations/{ctx['evaluation_id']}", headers=ctx["owner_headers"]
    ).json()
    assert evaluation["status"] == "collecting_responses"
    assert evaluation["response_deadline"] == "2030-06-01T00:00:00"

    vendor_detail = client.get(
        f"/api/v1/vendor-portal/proposals/{ctx['proposal_id']}", headers=ctx["vendor_headers"]
    ).json()
    assert vendor_detail["round"] == 1
    assert vendor_detail["reopened_reason"] == "Negociacion de precio"
    assert vendor_detail["cost_items"][0]["status"] == "inherited"
    assert vendor_detail["cost_items"][0]["source_proposal_version"] == 0


def test_editing_an_inherited_answer_marks_it_modified_and_keeps_provenance(
    client, seeded_actors, mongo_test_settings
) -> None:
    ctx = _setup_submitted_proposal(client, seeded_actors, mongo_test_settings)
    reopened = _reopen(client, ctx)
    version = reopened.json()["version"]

    edited = client.put(
        f"/api/v1/vendor-portal/proposals/{ctx['proposal_id']}/answers/{ctx['functional_id']}",
        json={"value": "Respuesta mejorada.", "expected_version": version},
        headers=ctx["vendor_headers"],
    )
    assert edited.status_code == 200
    answer = next(
        a for a in edited.json()["answers"] if a["requirement_id"] == ctx["functional_id"]
    )
    assert answer["status"] == "modified"
    assert answer["source_proposal_version"] == 0
    assert answer["value"] == "Respuesta mejorada."


def test_removing_an_inherited_cost_item_creates_a_removed_tombstone(
    client, seeded_actors, mongo_test_settings
) -> None:
    ctx = _setup_submitted_proposal(client, seeded_actors, mongo_test_settings)
    reopened = _reopen(client, ctx)
    version = reopened.json()["version"]

    detail = client.get(
        f"/api/v1/vendor-portal/proposals/{ctx['proposal_id']}", headers=ctx["vendor_headers"]
    ).json()
    cost_item_id = detail["cost_items"][0]["id"]

    removed = client.delete(
        f"/api/v1/vendor-portal/proposals/{ctx['proposal_id']}/cost-items/{cost_item_id}",
        params={"expected_version": version},
        headers=ctx["vendor_headers"],
    )
    assert removed.status_code == 200
    remaining = removed.json()["cost_items"]
    assert len(remaining) == 1  # tombstoned, not deleted
    assert remaining[0]["id"] == cost_item_id
    assert remaining[0]["status"] == "removed"


def test_removed_cost_item_excluded_from_new_tco(
    client, seeded_actors, mongo_test_settings
) -> None:
    ctx = _setup_submitted_proposal(client, seeded_actors, mongo_test_settings)
    reopened = _reopen(client, ctx)
    version = reopened.json()["version"]

    detail = client.get(
        f"/api/v1/vendor-portal/proposals/{ctx['proposal_id']}", headers=ctx["vendor_headers"]
    ).json()
    cost_item_id = detail["cost_items"][0]["id"]
    removed = client.delete(
        f"/api/v1/vendor-portal/proposals/{ctx['proposal_id']}/cost-items/{cost_item_id}",
        params={"expected_version": version},
        headers=ctx["vendor_headers"],
    )
    version = removed.json()["version"]

    preview = client.get(
        f"/api/v1/vendor-portal/proposals/{ctx['proposal_id']}/tco-preview",
        headers=ctx["vendor_headers"],
    )
    assert preview.status_code == 200
    assert preview.json()["grand_total"] == "0.00"

    submitted = client.post(
        f"/api/v1/vendor-portal/proposals/{ctx['proposal_id']}/submit",
        json={"expected_version": version},
        headers=ctx["vendor_headers"],
    )
    assert submitted.status_code == 200

    tco = client.get(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/proposals/{ctx['proposal_id']}/tco",
        headers=ctx["owner_headers"],
    )
    assert tco.status_code == 200
    assert tco.json()["grand_total"] == "0.00"


def test_second_round_submit_preserves_the_first_snapshot(
    client, seeded_actors, mongo_test_settings
) -> None:
    ctx = _setup_submitted_proposal(client, seeded_actors, mongo_test_settings)
    reopened = _reopen(client, ctx)
    version = reopened.json()["version"]
    client.post(
        f"/api/v1/vendor-portal/proposals/{ctx['proposal_id']}/submit",
        json={"expected_version": version},
        headers=ctx["vendor_headers"],
    )

    detail = client.get(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/proposals/{ctx['proposal_id']}",
        headers=ctx["owner_headers"],
    ).json()
    assert detail["status"] == "submitted"
    assert len(detail["snapshots"]) == 2
    assert detail["snapshots"][0]["round"] == 0
    assert detail["snapshots"][1]["round"] == 1


def test_reopen_rejected_after_max_rounds_reached(
    client, seeded_actors, mongo_test_settings
) -> None:
    ctx = _setup_submitted_proposal(client, seeded_actors, mongo_test_settings)
    reopened = _reopen(client, ctx)
    version = reopened.json()["version"]
    client.post(
        f"/api/v1/vendor-portal/proposals/{ctx['proposal_id']}/submit",
        json={"expected_version": version},
        headers=ctx["vendor_headers"],
    )

    second_reopen = _reopen(client, ctx, reason="Otra ronda")
    assert second_reopen.status_code == 409


def test_reopen_rejected_when_proposal_still_draft(
    client, seeded_actors, mongo_test_settings
) -> None:
    ctx = _setup_submitted_proposal(
        client, seeded_actors, mongo_test_settings, with_cost_item=False
    )
    # A fresh evaluation/proposal that was never submitted at all.
    owner_headers = ctx["owner_headers"]
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Never submitted", "description": ""},
        headers=owner_headers,
    ).json()["id"]
    proposal_id = client.post(
        f"/api/v1/evaluations/{evaluation_id}/vendors",
        json={"vendor_org_id": ctx["vendor_org_id"]},
        headers=owner_headers,
    ).json()["id"]

    response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/reopen",
        json={"reason": "x", "response_deadline": "2030-06-01T00:00:00Z"},
        headers=owner_headers,
    )
    assert response.status_code == 409


def test_reopen_requires_a_nonempty_reason(client, seeded_actors, mongo_test_settings) -> None:
    ctx = _setup_submitted_proposal(client, seeded_actors, mongo_test_settings)
    response = _reopen(client, ctx, reason="   ")
    assert response.status_code == 422


def test_non_owner_cannot_reopen(client, seeded_actors, mongo_test_settings) -> None:
    ctx = _setup_submitted_proposal(client, seeded_actors, mongo_test_settings)
    tenant_a = ctx["tenant_id"]
    evaluator_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluator_functional")], mongo_test_settings
    )
    response = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/proposals/{ctx['proposal_id']}/reopen",
        json={"reason": "x", "response_deadline": "2030-06-01T00:00:00Z"},
        headers=evaluator_headers,
    )
    assert response.status_code == 403


def test_non_reopened_proposal_and_second_reopen_in_same_round_are_independent(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    """Two submitted proposals under the same evaluation - only one gets
    reopened. ADR 0013: "No invitados... conservan su propuesta inicial".
    Both vendors must be linked while the evaluation is still `draft`
    (link_vendor is draft-only) - unlike the other tests in this file,
    vendor B has to be created and linked *before* publish, not bolted on
    afterward."""
    tenant_a, vendor_a_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    vendor_a_dev_headers = {DEV_ACTOR_HEADER: vendor_a_membership_id}
    vendor_a_org_id = client.get("/api/v1/me", headers=vendor_a_dev_headers).json()["vendor_org_id"]
    vendor_a_headers = vendor_bearer_headers_for(vendor_a_membership_id, mongo_test_settings)
    vendor_b_org_id, vendor_b_membership_id = _create_second_vendor(mongo_test_db, tenant_a)
    vendor_b_headers = vendor_bearer_headers_for(vendor_b_membership_id, mongo_test_settings)

    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Two vendors negotiation RFP", "description": ""},
        headers=owner_headers,
    ).json()["id"]
    functional_id = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "functional",
            "category": "Core",
            "title": "Req funcional",
            "description": "d",
            "priority": "important",
            "response_type": "text",
            "weight": 40.0,
            "required": False,
            "display_order": 1,
        },
        headers=owner_headers,
    ).json()["id"]
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "technical",
            "category": "Core",
            "title": "Req tecnico",
            "description": "d",
            "priority": "important",
            "response_type": "text",
            "weight": 20.0,
            "required": False,
            "display_order": 2,
        },
        headers=owner_headers,
    )
    proposal_a_id = client.post(
        f"/api/v1/evaluations/{evaluation_id}/vendors",
        json={"vendor_org_id": vendor_a_org_id},
        headers=owner_headers,
    ).json()["id"]
    proposal_b_id = client.post(
        f"/api/v1/evaluations/{evaluation_id}/vendors",
        json={"vendor_org_id": vendor_b_org_id},
        headers=owner_headers,
    ).json()["id"]
    approver_membership_id = seeded_actors[(tenant_a, "approver")]
    approver_headers = bearer_headers_for(approver_membership_id, mongo_test_settings)
    approve_and_publish(
        client, owner_headers, approver_membership_id, approver_headers, evaluation_id
    )

    client.put(
        f"/api/v1/vendor-portal/proposals/{proposal_a_id}/answers/{functional_id}",
        json={"value": "Respuesta A.", "expected_version": 1},
        headers=vendor_a_headers,
    )
    client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_a_id}/submit",
        json={"expected_version": 2},
        headers=vendor_a_headers,
    )
    client.put(
        f"/api/v1/vendor-portal/proposals/{proposal_b_id}/answers/{functional_id}",
        json={"value": "Respuesta B.", "expected_version": 1},
        headers=vendor_b_headers,
    )
    client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_b_id}/submit",
        json={"expected_version": 2},
        headers=vendor_b_headers,
    )
    client.post(f"/api/v1/evaluations/{evaluation_id}/start-evaluation", headers=owner_headers)

    ctx = {
        "evaluation_id": evaluation_id,
        "proposal_id": proposal_a_id,
        "owner_headers": owner_headers,
    }
    # Reopen only proposal A.
    reopened_a = _reopen(client, ctx)
    assert reopened_a.status_code == 200

    proposal_b_detail = client.get(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/proposals/{proposal_b_id}",
        headers=owner_headers,
    ).json()
    assert proposal_b_detail["status"] == "submitted"
    assert proposal_b_detail["round"] == 0
    assert proposal_b_detail["reopened_reason"] is None

    # Reopening B too (2nd reopen in the same round) must succeed and only
    # refresh the shared evaluation-wide deadline, not re-transition it.
    second_reopen = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/proposals/{proposal_b_id}/reopen",
        json={"reason": "Tambien negociar con B", "response_deadline": "2030-07-01T00:00:00Z"},
        headers=owner_headers,
    )
    assert second_reopen.status_code == 200
    evaluation = client.get(
        f"/api/v1/evaluations/{ctx['evaluation_id']}", headers=owner_headers
    ).json()
    assert evaluation["status"] == "collecting_responses"
    assert evaluation["response_deadline"] == "2030-07-01T00:00:00"


def test_reopen_cross_tenant_is_404(client, seeded_actors, mongo_test_settings) -> None:
    ctx = _setup_submitted_proposal(client, seeded_actors, mongo_test_settings)
    tenants = {tenant_id for tenant_id, _role in seeded_actors}
    other_tenant = next(t for t in tenants if t != ctx["tenant_id"])
    other_owner_key = (other_tenant, "evaluation_owner")
    if other_owner_key not in seeded_actors:
        pytest.skip("no second tenant owner seeded")
    other_owner_headers = bearer_headers_for(seeded_actors[other_owner_key], mongo_test_settings)
    response = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/proposals/{ctx['proposal_id']}/reopen",
        json={"reason": "x", "response_deadline": "2030-06-01T00:00:00Z"},
        headers=other_owner_headers,
    )
    assert response.status_code == 404
