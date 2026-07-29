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

    # Flip a character inside the signature segment, but never its very last
    # character. An HS256 signature is 32 bytes -> 43 base64url characters,
    # and base64's final character of a length that isn't a multiple of 3
    # bytes only encodes 4 significant bits (the other 2 are padding,
    # discarded on decode) - so occasionally a *different* last character
    # still decodes to byte-identical signature bytes, making the "tampered"
    # token spuriously still valid (this was flaky in CI: the payload embeds
    # the real iat/exp, so the signature - and which characters are
    # boundary-safe - differs run to run). Any other position is a full
    # 6-bit-significant slot, so tampering it always changes the decoded
    # bytes, deterministically.
    header_b64, payload_b64, signature_b64 = token.split(".")
    index = len(signature_b64) - 2
    flipped_char = "A" if signature_b64[index] != "A" else "B"
    tampered_signature = signature_b64[:index] + flipped_char + signature_b64[index + 1 :]
    tampered = f"{header_b64}.{payload_b64}.{tampered_signature}"

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
