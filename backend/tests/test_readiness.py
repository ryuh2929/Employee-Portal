from fastapi.testclient import TestClient

from app.main import app


def test_readiness_with_postgres() -> None:
    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "connected"}
