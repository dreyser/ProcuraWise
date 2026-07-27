from procurawise.proposals.models import Proposal, ProposalAnswer


def test_proposal_create_defaults_to_draft_version_one() -> None:
    proposal = Proposal.create(tenant_id="t", evaluation_id="e", vendor_org_id="v")
    assert proposal.status == "draft"
    assert proposal.version == 1
    assert proposal.answers == []
    assert proposal.snapshot is None
    assert proposal.submitted_at is None


def test_proposal_round_trips_through_document_with_answers() -> None:
    proposal = Proposal.create(tenant_id="t", evaluation_id="e", vendor_org_id="v")
    from dataclasses import replace
    from datetime import UTC, datetime

    answer = ProposalAnswer(
        requirement_id="r1", value="compliant", vendor_comment=None, updated_at=datetime.now(UTC)
    )
    proposal = replace(proposal, answers=[answer])
    restored = Proposal.from_document(proposal.to_document())
    assert restored == proposal
