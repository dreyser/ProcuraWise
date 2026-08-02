from procurawise.ai.models import AIExecution, TokenUsage


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
