import time

import pytest

from procurawise.identity.jwt_provider import (
    TokenExpiredError,
    TokenInvalidError,
    create_access_token,
    create_pre_session_token,
    decode_token,
)
from procurawise.shared.config import Settings
from procurawise.shared.context import ActorContext


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


def _context() -> ActorContext:
    return ActorContext(
        membership_id="m1",
        user_id="u1",
        tenant_id="t1",
        tenant_name="Acme",
        role="evaluation_owner",
        vendor_org_id=None,
        display_name="Owner",
    )


def test_access_token_round_trips_actor_context() -> None:
    settings = _settings()
    token, expires_in = create_access_token(_context(), settings)
    assert expires_in == settings.access_token_ttl_minutes * 60
    claims = decode_token(token, settings, expected_use="access")
    assert claims["membership_id"] == "m1"
    assert claims["tenant_id"] == "t1"
    assert claims["role"] == "evaluation_owner"
    assert claims["sub"] == "u1"


def test_pre_session_token_carries_only_sub() -> None:
    settings = _settings()
    token, _ = create_pre_session_token("u1", settings)
    claims = decode_token(token, settings, expected_use="pre_session")
    assert claims["sub"] == "u1"
    assert "tenant_id" not in claims


def test_decode_rejects_wrong_token_use() -> None:
    settings = _settings()
    token, _ = create_pre_session_token("u1", settings)
    with pytest.raises(TokenInvalidError):
        decode_token(token, settings, expected_use="access")


def test_decode_rejects_tampered_signature() -> None:
    settings = _settings()
    token, _ = create_access_token(_context(), settings)
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(TokenInvalidError):
        decode_token(tampered, settings, expected_use="access")


def test_decode_rejects_token_signed_with_different_secret() -> None:
    settings = _settings(jwt_secret="x" * 32)
    other_settings = _settings(jwt_secret="y" * 32)
    token, _ = create_access_token(_context(), settings)
    with pytest.raises(TokenInvalidError):
        decode_token(token, other_settings, expected_use="access")


def test_decode_rejects_expired_token() -> None:
    settings = _settings(access_token_ttl_minutes=0)
    token, _ = create_access_token(_context(), settings)
    time.sleep(1)
    with pytest.raises(TokenExpiredError):
        decode_token(token, settings, expected_use="access")
