import pytest

from procurawise.identity.dev_provider import DEV_ACTOR_HEADER
from tests.conftest import (
    approve_and_publish,
    bearer_headers_for,
    unique_actor_by_role,
    vendor_bearer_headers_for,
)

pytestmark = pytest.mark.docker


@pytest.fixture(autouse=True)
def _clean_audit_events(mongo_test_db):
    yield
    mongo_test_db["audit_events"].delete_many({})


def _events_for(mongo_test_db, evaluation_id: str) -> list[dict]:
    return list(
        mongo_test_db["audit_events"].find({"evaluation_id": evaluation_id}).sort("occurred_at", 1)
    )


def _submitted_proposal(client, seeded_actors, mongo_test_settings):
    """Builds one evaluation, in `evaluating` status, with exactly one
    submitted proposal - the shared setup for every scoring test below."""
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    vendor_dev_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_dev_headers).json()["vendor_org_id"]
    vendor_headers = vendor_bearer_headers_for(vendor_membership_id, mongo_test_settings)

    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Scoring Audit RFP", "description": ""},
        headers=owner_headers,
    ).json()["id"]

    functional_id = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "functional",
            "category": "Core",
            "title": "Req 1",
            "description": "d",
            "priority": "important",
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
            "title": "Req 2",
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
    client.put(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/answers/{functional_id}",
        json={"value": "answer", "expected_version": 1},
        headers=vendor_headers,
    )
    # Fase 20: a nonzero cost item (currency == the evaluation's default
    # base_currency MXN, so no FXRate needs seeding here) makes TCO
    # "available" rather than "no_comparable" - needed by
    # test_complete_evaluation_generates_exactly_one_event below, which
    # must reach a real economic-complete state to call /complete.
    client.post(
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
            "expected_version": 2,
        },
        headers=vendor_headers,
    )
    client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/submit",
        json={"expected_version": 3},
        headers=vendor_headers,
    )
    client.post(f"/api/v1/evaluations/{evaluation_id}/start-evaluation", headers=owner_headers)

    return evaluation_id, proposal_id, functional_id, technical_id, owner_headers


def test_score_created_and_updated_generate_exactly_the_expected_events(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    """Plan §6/§13/§10: score creation and update are audited with the
    numeric score value and requirement_id, but never the free-text comment
    (CLAUDE.md: comentarios de scoring nunca entran al audit trail)."""
    evaluation_id, proposal_id, requirement_id, _technical_id, owner_headers = _submitted_proposal(
        client, seeded_actors, mongo_test_settings
    )

    created = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/scores/{requirement_id}",
        json={"score": 4, "comment": "sensitive scoring rationale", "version": None},
        headers=owner_headers,
    )
    assert created.status_code == 200
    score_id = created.json()["id"]

    updated = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/scores/{requirement_id}",
        json={"score": 5, "comment": "sensitive scoring rationale", "version": 1},
        headers=owner_headers,
    )
    assert updated.status_code == 200

    events = _events_for(mongo_test_db, evaluation_id)
    score_events = [e for e in events if e["resource_type"] == "score"]
    assert [e["action"] for e in score_events] == ["score_created", "score_updated"]

    created_event, updated_event = score_events
    assert created_event["resource_id"] == score_id
    assert created_event["proposal_id"] == proposal_id
    assert created_event["version"] == 1
    assert created_event["metadata"] == {"requirement_id": requirement_id, "score": 4}

    assert updated_event["resource_id"] == score_id
    assert updated_event["version"] == 2
    assert updated_event["metadata"] == {"requirement_id": requirement_id, "score": 5}

    # The scoring comment must never appear anywhere in the persisted event.
    for event in score_events:
        assert "sensitive scoring rationale" not in str(event)


def test_stale_score_version_conflict_does_not_generate_an_event(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    evaluation_id, proposal_id, requirement_id, _technical_id, owner_headers = _submitted_proposal(
        client, seeded_actors, mongo_test_settings
    )
    client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/scores/{requirement_id}",
        json={"score": 3, "comment": None, "version": None},
        headers=owner_headers,
    )

    conflicting = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/scores/{requirement_id}",
        json={"score": 5, "comment": None, "version": 999},
        headers=owner_headers,
    )
    assert conflicting.status_code == 409

    events = _events_for(mongo_test_db, evaluation_id)
    score_events = [e for e in events if e["resource_type"] == "score"]
    assert len(score_events) == 1  # only the initial score_created, not a second event
    assert score_events[0]["action"] == "score_created"


def test_complete_evaluation_generates_exactly_one_event(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    evaluation_id, proposal_id, requirement_id, technical_id, owner_headers = _submitted_proposal(
        client, seeded_actors, mongo_test_settings
    )
    client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/scores/{requirement_id}",
        json={"score": 5, "comment": None, "version": None},
        headers=owner_headers,
    )
    client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/scores/{technical_id}",
        json={"score": 5, "comment": None, "version": None},
        headers=owner_headers,
    )
    # Fase 20: complete_evaluation() now also requires the economic
    # assessment to be complete (see _submitted_proposal's cost item above).
    client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/economic-assessment",
        json={
            "commercial_scores": [
                {"criterion_key": key, "score": 3, "comment": None}
                for key in [
                    "payment_terms",
                    "price_protection",
                    "contractual_flexibility",
                    "discounts_incentives",
                    "billing_transparency",
                ]
            ],
            "risk_scores": [
                {"criterion_key": key, "score": 3, "comment": None}
                for key in [
                    "variable_cost_exposure",
                    "increases_indexation",
                    "assumptions_exclusions",
                    "fx_fiscal_regulatory",
                    "exit_portability_lockin",
                ]
            ],
        },
        headers=owner_headers,
    )

    completed = client.post(f"/api/v1/evaluations/{evaluation_id}/complete", headers=owner_headers)
    assert completed.status_code == 200

    events = _events_for(mongo_test_db, evaluation_id)
    complete_events = [e for e in events if e["action"] == "evaluation_completed"]
    assert len(complete_events) == 1
    assert complete_events[0]["metadata"] == {
        "from_status": "evaluating",
        "to_status": "completed",
    }


def test_rejected_complete_does_not_generate_an_event(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    """complete_evaluation's own precondition (not fully scored) must reject
    without ever recording an evaluation_completed event."""
    evaluation_id, _proposal_id, _requirement_id, _technical_id, owner_headers = (
        _submitted_proposal(client, seeded_actors, mongo_test_settings)
    )

    rejected = client.post(f"/api/v1/evaluations/{evaluation_id}/complete", headers=owner_headers)
    assert rejected.status_code == 400  # not all submitted proposals are fully scored

    events = _events_for(mongo_test_db, evaluation_id)
    assert "evaluation_completed" not in [e["action"] for e in events]
