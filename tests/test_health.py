from fastapi.testclient import TestClient

from datapilot.api.app import app

client = TestClient(app)


def test_live_health_check() -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "datapilot",
        "version": "1.1.0",
        "focus": "agent-backend",
    }


def test_ready_health_check() -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "environment": "development",
    }
