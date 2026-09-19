"""
LeadRescue AI — API Integration Tests
Tests all Phase 2 backend REST API endpoints using TestClient.
"""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_create_and_get_lead_api():
    payload = {
        "customer_name": "Rahul Sharma",
        "customer_phone": "+91-9876543210",
        "customer_email": "rahul@example.com",
        "source": "whatsapp",
        "raw_message": "I need 10 CNC machines. Need delivery to Pune urgently.",
    }

    # Create lead
    res_create = client.post("/api/leads", json=payload)
    assert res_create.status_code == 201
    data = res_create.json()
    assert data["customer_name"] == "Rahul Sharma"
    assert data["source"] == "whatsapp"
    lead_id = data["lead_id"]

    # Get lead
    res_get = client.get(f"/api/leads/{lead_id}")
    assert res_get.status_code == 200
    assert res_get.json()["lead_id"] == lead_id

    # Get lead audit trail
    res_audit = client.get(f"/api/leads/{lead_id}/audit")
    assert res_audit.status_code == 200
    audit_events = res_audit.json()
    assert len(audit_events) >= 1
    assert audit_events[0]["action"] == "lead_received"


def test_opt_out_lead_creation():
    """Lead 5 Sunita Rao opt-out detection test."""
    payload = {
        "customer_name": "Sunita Rao",
        "customer_email": "sunita@example.com",
        "source": "manual",
        "raw_message": "Please remove me from your list.",
    }
    res = client.post("/api/leads", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["lifecycle_status"] == "opted_out"


def test_list_leads_and_filtering():
    res = client.get("/api/leads?source=whatsapp")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_get_followups():
    res = client.get("/api/followups")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_get_and_update_config_api():
    # GET config
    res_get = client.get("/api/config")
    assert res_get.status_code == 200
    assert "response_target_minutes" in res_get.json()["config_value"]

    # PUT config
    res_put = client.put(
        "/api/config",
        json={"config_value": {"response_target_minutes": 25}},
    )
    assert res_put.status_code == 200
    assert res_put.json()["config_value"]["response_target_minutes"] == 25


def test_create_lead_invalid_payload():
    """Invalid payload rejected with 422 Unprocessable Entity."""
    res = client.post("/api/leads", json={"invalid_field": True})
    assert res.status_code == 422
