import pytest
from fastapi.testclient import TestClient

from procurawise.api.main import app

pytestmark = pytest.mark.docker

client = TestClient(app)


def test_health_ready_returns_200_when_dependencies_are_up() -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"] == {"mongodb": True, "storage": True}
