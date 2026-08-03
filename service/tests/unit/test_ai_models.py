from procurawise.ai.models import AIExecution, TokenUsage
from procurawise.ai.schemas import AIScoreSuggestionCandidate


def test_token_usage_round_trip() -> None:
    usage = TokenUsage(prompt_tokens=120, completion_tokens=80, total_tokens=200)
    assert TokenUsage.from_document(usage.to_document()) == usage


def test_ai_execution_create_defaults() -> None:
    execution = AIExecution.create(
        tenant_id="tenant-1",
        evaluation_id="eval-1",
        requested_by_membership_id="membership-1",
        use_case="requirement_generation",
        provider="azure_openai",
        prompt_template="requirement_generation",
        prompt_version="v1",
        retention_days=365,
    )
    assert execution.status == "queued"
    assert execution.candidates is None
    assert execution.accepted_requirement_ids == []
    assert execution.error is None
    assert execution.completed_at is None
    assert execution.expires_at > execution.created_at
    # Fase 14 (ADR 0011): both default to empty, not None - source_catalog is
    # always a list (possibly empty if no research provider found anything),
    # never absent.
    assert execution.source_catalog == []
    assert execution.warnings == []
    # Fase 18 (ADR 0022): a requirement_generation job never populates these.
    assert execution.proposal_id is None
    assert execution.snapshot_id is None


def test_ai_execution_create_with_score_suggestion_use_case() -> None:
    execution = AIExecution.create(
        tenant_id="tenant-1",
        evaluation_id="eval-1",
        requested_by_membership_id="membership-1",
        use_case="score_suggestion",
        provider="azure_openai",
        prompt_template="score_suggestion",
        prompt_version="v1",
        retention_days=365,
        proposal_id="proposal-1",
        snapshot_id="snapshot-1",
    )
    assert execution.use_case == "score_suggestion"
    assert execution.proposal_id == "proposal-1"
    assert execution.snapshot_id == "snapshot-1"
    restored = AIExecution.from_document(execution.to_document())
    assert restored == execution


def test_ai_execution_from_document_defaults_missing_proposal_fields_to_none() -> None:
    # A requirement_generation execution persisted before Fase 18 never wrote
    # proposal_id/snapshot_id keys at all - from_document must not KeyError.
    execution = AIExecution.create(
        tenant_id="tenant-1",
        evaluation_id="eval-1",
        requested_by_membership_id="membership-1",
        use_case="requirement_generation",
        provider="azure_openai",
        prompt_template="requirement_generation",
        prompt_version="v1",
        retention_days=365,
    )
    doc = execution.to_document()
    del doc["proposal_id"]
    del doc["snapshot_id"]
    restored = AIExecution.from_document(doc)
    assert restored.proposal_id is None
    assert restored.snapshot_id is None


def test_ai_score_suggestion_candidate_round_trip() -> None:
    candidate = AIScoreSuggestionCandidate(
        requirement_id="req-1",
        suggested_score=3,
        risk_flags=["incomplete_answer", "missing_evidence"],
        rationale="La respuesta no cubre el requisito de disponibilidad.",
    )
    restored = AIScoreSuggestionCandidate.model_validate(candidate.model_dump())
    assert restored == candidate


def test_ai_execution_round_trip_with_source_catalog_and_warnings() -> None:
    execution = AIExecution.create(
        tenant_id="tenant-1",
        evaluation_id="eval-1",
        requested_by_membership_id="membership-1",
        use_case="requirement_generation",
        provider="azure_openai",
        prompt_template="requirement_generation",
        prompt_version="v1",
        retention_days=365,
    )
    succeeded = AIExecution(
        **{
            **execution.__dict__,
            "status": "succeeded",
            "source_catalog": [
                {
                    "source_type": "curated_source",
                    "source_id": "src-1",
                    "title": "T",
                    "url": "https://x",
                }
            ],
            "warnings": [
                {
                    "code": "research_provider_unavailable",
                    "source_type": "web_search",
                    "message": "no disponible",
                }
            ],
        }
    )
    restored = AIExecution.from_document(succeeded.to_document())
    assert restored == succeeded


def test_ai_execution_round_trip_with_candidates() -> None:
    execution = AIExecution.create(
        tenant_id="tenant-1",
        evaluation_id="eval-1",
        requested_by_membership_id="membership-1",
        use_case="requirement_generation",
        provider="azure_openai",
        prompt_template="requirement_generation",
        prompt_version="v1",
        retention_days=365,
    )
    succeeded = AIExecution(
        **{
            **execution.__dict__,
            "status": "succeeded",
            "model": "gpt-4o-mini",
            "token_usage": TokenUsage(100, 50, 150),
            "cost_estimate": 0.01,
            "latency_ms": 1200,
            "candidates": [{"title": "Sample requirement"}],
        }
    )
    doc = succeeded.to_document()
    restored = AIExecution.from_document(doc)
    assert restored == succeeded
