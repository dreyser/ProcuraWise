import time

from fastapi.testclient import TestClient

from procurawise.api.main import app

client = TestClient(app)


def test_health_ready_returns_503_when_mongo_unreachable(monkeypatch) -> None:
    # Port 1 is a closed/unreachable port on localhost - stands in for "Mongo is down"
    # without requiring Docker. mongodb_server_selection_timeout_ms keeps this fast.
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:1")
    monkeypatch.setenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS", "500")

    started = time.monotonic()
    response = client.get("/health/ready")
    elapsed = time.monotonic() - started

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["checks"]["mongodb"] is False
    assert elapsed < 5, "readiness check must fail fast, not hang"


def test_health_ready_response_never_contains_connection_string(monkeypatch) -> None:
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:1")
    monkeypatch.setenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS", "500")

    response = client.get("/health/ready")

    assert "mongodb://" not in response.text
    assert "AccountKey" not in response.text
