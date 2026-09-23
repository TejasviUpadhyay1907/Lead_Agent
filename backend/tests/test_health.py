"""
LeadRescue AI — Foundation Tests
Verifies FastAPI application import and health endpoint.
"""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    """Verify GET /health returns 200 and expected status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "leadrescue-ai"
    assert data == {"status": "healthy", "service": "leadrescue-ai"}
