"""Fase 26 (Hardening, plan Bloque 1) - CORS + security headers middleware
(api/main.py). Hits /health/live (never touches Mongo/Blob) so this stays a
fast unit test, not a `docker`-marked one."""

from fastapi.testclient import TestClient

from procurawise.api.main import app

client = TestClient(app)


def test_every_response_carries_baseline_security_headers() -> None:
    response = client.get("/health/live")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_hsts_is_absent_outside_production() -> None:
    """Settings.environment defaults to "local" for the test process - HSTS
    would be actively harmful (or at least pointless) without HTTPS actually
    terminating in front of this process."""
    response = client.get("/health/live")

    assert "Strict-Transport-Security" not in response.headers


def test_cors_preflight_rejects_an_unlisted_origin() -> None:
    """cors_allowed_origins defaults to "" (deny-all) - a preflight from any
    origin gets no Access-Control-Allow-Origin header back, so the browser
    blocks the real request client-side."""
    response = client.options(
        "/health/live",
        headers={
            "Origin": "https://not-allowed.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in {k.lower() for k in response.headers}
