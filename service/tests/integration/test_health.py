from fastapi.testclient import TestClient

from procurawise.api.main import app

client = TestClient(app)


def test_health_live_returns_ok() -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
