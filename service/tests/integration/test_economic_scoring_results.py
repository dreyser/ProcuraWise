"""Fase 20 acceptance criterion (backlog.md fila 20): "Formula final 40/20/40
+ flags eliminatorios calcula correctamente contra casos de prueba fijos."
This file proves the full get_results()/complete_evaluation() integration
directly against real Mongo, with fixed numeric inputs and exact expected
outputs - not just the pure-function unit tests in test_economic_formulas.py."""

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

_COMMERCIAL_KEYS = [
    "payment_terms",
    "price_protection",
    "contractual_flexibility",
    "discounts_incentives",
    "billing_transparency",
]
_RISK_KEYS = [
    "variable_cost_exposure",
    "increases_indexation",
    "assumptions_exclusions",
    "fx_fiscal_regulatory",
    "exit_portability_lockin",
]


def _max_scores_body() -> dict:
    return {
        "commercial_scores": [
            {"criterion_key": k, "score": 5, "comment": "Excelente"} for k in _COMMERCIAL_KEYS
        ],
        "risk_scores": [
            {"criterion_key": k, "score": 5, "comment": "Excelente"} for k in _RISK_KEYS
        ],
    }


def _create_second_vendor(mongo_test_db, tenant_id: str) -> tuple[str, str]:
    """Mirrors tests/security/test_vendor_isolation.py's
    _create_second_vendor_contact: dev_seed only ever seeds one
    VendorOrganization per tenant, so TCO normalization across 2+ real
    proposals needs a genuinely second org+contact created directly, with
    both Agreements pre-accepted so it can act in the vendor portal.
    Returns (vendor_org_id, membership_id)."""
    users = UserRepository(mongo_test_db)
    vendor_orgs = VendorOrganizationRepository(mongo_test_db)
    memberships = MembershipRepository(mongo_test_db)

    user = User.create(display_name="Vendor Contact B", email="vendor.b.economic@dev.local")
    users.insert(user.to_document())
    vendor_org = VendorOrganization.create(tenant_id=tenant_id, name="Proveedor Dos (economic)")
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


def _add_cost_item(
    client, vendor_headers, proposal_id: str, *, quantity: str, expected_version: int
):
    response = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/cost-items",
        json={
            "concept": "Licencia anual",
            "category": "recurring",
            "billing_unit": "usuario",
            "quantity": quantity,
            "unit_price": "100",
            "currency": "MXN",
            "frequency_per_year": "1",
            "year_start": 1,
            "year_end": 1,
            "cost_type": "recurring",
            "expected_version": expected_version,
        },
        headers=vendor_headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["version"]


def _build_two_proposal_evaluation(client, seeded_actors, mongo_test_settings, mongo_test_db):
    """One evaluation with 1 functional (weight 40) + 1 technical (weight
    20) requirement, both important (not mandatory), linked to two distinct
    vendor orgs. Vendor A's cost item totals 1000 MXN, vendor B's totals
    2000 MXN - vendor A must therefore get TCO_pct=100, vendor B
    TCO_pct=50 (1000/2000*100), by calculate_tco_normalized_pct's own
    definition. Returns (evaluation_id, proposal_a_id, proposal_b_id,
    owner_headers)."""
    tenant_a, vendor_a_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    vendor_a_headers = vendor_bearer_headers_for(vendor_a_membership_id, mongo_test_settings)
    vendor_a_org_id = client.get(
        "/api/v1/me", headers={DEV_ACTOR_HEADER: vendor_a_membership_id}
    ).json()["vendor_org_id"]

    vendor_b_org_id, vendor_b_membership_id = _create_second_vendor(mongo_test_db, tenant_a)
    vendor_b_headers = vendor_bearer_headers_for(vendor_b_membership_id, mongo_test_settings)

    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Economic scoring RFP", "description": ""},
        headers=owner_headers,
    ).json()["id"]
    client.post(
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
    )
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

    version_a = _add_cost_item(
        client, vendor_a_headers, proposal_a_id, quantity="10", expected_version=1
    )
    client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_a_id}/submit",
        json={"expected_version": version_a},
        headers=vendor_a_headers,
    )
    version_b = _add_cost_item(
        client, vendor_b_headers, proposal_b_id, quantity="20", expected_version=1
    )
    client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_b_id}/submit",
        json={"expected_version": version_b},
        headers=vendor_b_headers,
    )

    client.post(f"/api/v1/evaluations/{evaluation_id}/start-evaluation", headers=owner_headers)
    return evaluation_id, proposal_a_id, proposal_b_id, owner_headers


def _score_functional_and_technical(client, owner_headers, evaluation_id, proposal_id) -> None:
    requirements = client.get(f"/api/v1/evaluations/{evaluation_id}", headers=owner_headers).json()[
        "requirements"
    ]
    functional_id = next(r["id"] for r in requirements if r["dimension"] == "functional")
    technical_id = next(r["id"] for r in requirements if r["dimension"] == "technical")
    for requirement_id in (functional_id, technical_id):
        response = client.put(
            f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/scores/{requirement_id}",
            json={"score": 5, "comment": None},
            headers=owner_headers,
        )
        assert response.status_code == 200, response.text


def test_two_proposals_final_result_matches_fixed_formula(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    evaluation_id, proposal_a_id, proposal_b_id, owner_headers = _build_two_proposal_evaluation(
        client, seeded_actors, mongo_test_settings, mongo_test_db
    )
    for proposal_id in (proposal_a_id, proposal_b_id):
        _score_functional_and_technical(client, owner_headers, evaluation_id, proposal_id)
        economic = client.put(
            f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/economic-assessment",
            json=_max_scores_body(),
            headers=owner_headers,
        )
        assert economic.status_code == 200, economic.text

    results = client.get(f"/api/v1/evaluations/{evaluation_id}/results", headers=owner_headers)
    assert results.status_code == 200
    body = results.json()
    assert body["result_status"] == "final"
    assert body["is_final"] is True

    by_proposal = {p["proposal_id"]: p for p in body["proposals"]}
    proposal_a = by_proposal[proposal_a_id]
    proposal_b = by_proposal[proposal_b_id]

    # commercial_pct=risk_pct=100 for both (all-5 rubric); TCO_pct differs:
    # A=100 (lowest), B=50 (1000/2000*100). economic_points = 40 x
    # [0.70x(tco/100) + 0.15x1 + 0.15x1].
    assert proposal_a["economic"]["status"] == "available"
    assert proposal_a["economic"]["earned_points"] == 40.0
    assert proposal_b["economic"]["status"] == "available"
    assert proposal_b["economic"]["earned_points"] == 26.0

    # functional(40) + technical(20), both scored 5/5 -> full marks.
    assert proposal_a["final_result"] == {"total_points": 100.0, "maximum_points": 100.0}
    assert proposal_b["final_result"] == {"total_points": 86.0, "maximum_points": 100.0}


def test_final_result_absent_until_economic_assessment_is_complete(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    evaluation_id, proposal_a_id, proposal_b_id, owner_headers = _build_two_proposal_evaluation(
        client, seeded_actors, mongo_test_settings, mongo_test_db
    )
    _score_functional_and_technical(client, owner_headers, evaluation_id, proposal_a_id)
    _score_functional_and_technical(client, owner_headers, evaluation_id, proposal_b_id)

    results = client.get(f"/api/v1/evaluations/{evaluation_id}/results", headers=owner_headers)
    body = results.json()
    assert body["result_status"] == "partial"
    assert body["is_final"] is False
    assert body["scoring_status"] == "incomplete"
    for proposal in body["proposals"]:
        assert proposal["final_result"] is None
        assert proposal["economic"]["status"] == "not_available"

    complete_attempt = client.post(
        f"/api/v1/evaluations/{evaluation_id}/complete", headers=owner_headers
    )
    assert complete_attempt.status_code == 400

    # Completing only proposal A's economic assessment still leaves the
    # evaluation partial (proposal B's is still missing).
    only_a = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_a_id}/economic-assessment",
        json=_max_scores_body(),
        headers=owner_headers,
    )
    assert only_a.status_code == 200
    results_after_a = client.get(
        f"/api/v1/evaluations/{evaluation_id}/results", headers=owner_headers
    ).json()
    assert results_after_a["result_status"] == "partial"
    by_proposal = {p["proposal_id"]: p for p in results_after_a["proposals"]}
    assert by_proposal[proposal_a_id]["final_result"] is not None
    assert by_proposal[proposal_b_id]["final_result"] is None


def test_mandatory_alert_coexists_with_final_result(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    """VS-2B's mandatory_alert (Requirement.priority == 'mandatory' + a low
    score) must keep working unchanged once the final 40/20/40 formula is
    layered on top - it is informational only, never a block on completing
    the evaluation (CLAUDE.md: no adjudicacion automatica)."""
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    vendor_headers = vendor_bearer_headers_for(vendor_membership_id, mongo_test_settings)
    vendor_org_id = client.get(
        "/api/v1/me", headers={DEV_ACTOR_HEADER: vendor_membership_id}
    ).json()["vendor_org_id"]

    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Mandatory alert RFP", "description": ""},
        headers=owner_headers,
    ).json()["id"]
    functional_id = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "functional",
            "category": "Core",
            "title": "Requisito obligatorio",
            "description": "d",
            "priority": "mandatory",
            "response_type": "text",
            "weight": 40.0,
            "required": False,
            "display_order": 1,
        },
        headers=owner_headers,
    ).json()["id"]
    technical_id = client.post(
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
    ).json()["id"]
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
    version = _add_cost_item(client, vendor_headers, proposal_id, quantity="10", expected_version=1)
    client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/submit",
        json={"expected_version": version},
        headers=vendor_headers,
    )
    client.post(f"/api/v1/evaluations/{evaluation_id}/start-evaluation", headers=owner_headers)

    scored_functional = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/scores/{functional_id}",
        json={"score": 1, "comment": "No cumple del todo"},
        headers=owner_headers,
    )
    assert scored_functional.status_code == 200
    assert scored_functional.json()["mandatory_alert"] is True
    assert scored_functional.json()["weighted_points"] == 8.0

    client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/scores/{technical_id}",
        json={"score": 5, "comment": None},
        headers=owner_headers,
    )
    client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/economic-assessment",
        json=_max_scores_body(),
        headers=owner_headers,
    )

    results = client.get(f"/api/v1/evaluations/{evaluation_id}/results", headers=owner_headers)
    body = results.json()
    [proposal_result] = body["proposals"]
    assert proposal_result["mandatory_alerts_count"] == 1
    # functional 8.0 + technical 20.0 + economic 40.0 (TCO is the only
    # submitted proposal, so it is trivially its own lowest -> 100%).
    assert proposal_result["final_result"] == {"total_points": 68.0, "maximum_points": 100.0}
    assert body["result_status"] == "final"

    complete = client.post(f"/api/v1/evaluations/{evaluation_id}/complete", headers=owner_headers)
    assert complete.status_code == 200
    assert complete.json()["status"] == "completed"
