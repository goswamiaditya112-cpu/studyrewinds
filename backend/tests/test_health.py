from fastapi.testclient import TestClient

def test_health_endpoint(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["project"] == "StudyRewinds"
    assert data["environment"] == "development"

def test_db_health_endpoint(client: TestClient):
    response = client.get("/health/db")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "postgresql"
    assert data["pgvector_installed"] is True
    assert "pgvector_version" in data
