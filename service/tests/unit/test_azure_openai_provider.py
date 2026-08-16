from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from openai import RateLimitError

from procurawise.ai.azure_openai_provider import AzureOpenAIProvider
from procurawise.ai.models import AIRequest
from procurawise.shared.config import Settings


def _provider() -> AzureOpenAIProvider:
    return AzureOpenAIProvider(
        endpoint="https://example.openai.azure.com",
        api_key="test-key",
        deployment="gpt-test-deployment",
        api_version="2024-10-21",
        timeout_seconds=5,
    )


def _request() -> AIRequest:
    return AIRequest(
        system_prompt="system",
        user_prompt="user",
        response_schema={"type": "object"},
        max_tokens=100,
        timeout_seconds=5,
    )


def _fake_sdk_response(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        model="gpt-test-deployment",
    )


def test_from_settings_requires_full_azure_openai_config() -> None:
    settings = Settings(_env_file=None)
    with pytest.raises(ValueError, match="azure_openai"):
        AzureOpenAIProvider.from_settings(settings)


def test_from_settings_builds_provider_when_configured() -> None:
    settings = Settings(
        _env_file=None,
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_api_key="key",
        azure_openai_deployment="deployment",
    )
    provider = AzureOpenAIProvider.from_settings(settings)
    assert provider is not None


def test_generate_maps_sdk_response_to_ai_response() -> None:
    provider = _provider()
    provider._client.chat.completions.create = MagicMock(  # type: ignore[method-assign]
        return_value=_fake_sdk_response('{"candidates": []}')
    )

    response = provider.generate(_request())

    assert response.parsed_output == {"candidates": []}
    assert response.token_usage.total_tokens == 15
    assert response.model == "gpt-test-deployment"
    assert response.finish_reason == "stop"

    call_kwargs = provider._client.chat.completions.create.call_args.kwargs
    assert call_kwargs["max_completion_tokens"] == 100
    assert "max_tokens" not in call_kwargs
    assert "temperature" not in call_kwargs


def test_generate_retries_once_on_rate_limit_then_succeeds(monkeypatch) -> None:
    monkeypatch.setattr("procurawise.ai.azure_openai_provider.time.sleep", lambda _seconds: None)
    provider = _provider()
    rate_limit_error = RateLimitError(
        message="rate limited",
        response=MagicMock(status_code=429, headers={}),
        body=None,
    )
    provider._client.chat.completions.create = MagicMock(  # type: ignore[method-assign]
        side_effect=[rate_limit_error, _fake_sdk_response("{}")]
    )

    response = provider.generate(_request())

    assert response.parsed_output == {}
    assert provider._client.chat.completions.create.call_count == 2


def test_generate_raises_after_exhausting_retries(monkeypatch) -> None:
    monkeypatch.setattr("procurawise.ai.azure_openai_provider.time.sleep", lambda _seconds: None)
    provider = _provider()
    rate_limit_error = RateLimitError(
        message="rate limited",
        response=MagicMock(status_code=429, headers={}),
        body=None,
    )
    provider._client.chat.completions.create = MagicMock(  # type: ignore[method-assign]
        side_effect=[rate_limit_error, rate_limit_error]
    )

    with pytest.raises(RateLimitError):
        provider.generate(_request())
