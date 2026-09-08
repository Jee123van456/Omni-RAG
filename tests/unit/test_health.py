from fastapi import status

def test_health_check(client):
    """
    Test that /health endpoint is running and returns standard metadata.
    """
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert data["version"] == "1.0.0"

def test_api_health_check(client):
    """
    Test that /api/health endpoint returns connected status for database and redis.
    """
    response = client.get("/api/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "healthy"
    assert data["services"]["database"] == "connected"
    assert data["services"]["redis"] == "connected"
