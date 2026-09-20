"""
LeadRescue AI — Integration Tests for POST /api/leads/{id}/analyze Endpoint
"""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_analyze_lead_endpoint_integration():
    """
    Test POST /api/leads/{id}/analyze:
    1. Creates lead.
    2. Invokes POST /api/leads/{id}/analyze.
    3. Verifies AI understanding AND PolicyEngine deterministic decision fields (score=93, priority=HOT, lifecycle_status=analyzed).
    4. Verifies audit event 'lead_analyzed' is recorded with score details.
    """
    # 1. Create Lead
    create_res = client.post(
        "/api/leads",
        json={
            "customer_name": "Rahul Sharma",
            "customer_phone": "+91-9876543210",
            "customer_email": "rahul@example.com",
            "source": "whatsapp",
            "raw_message": "I need 10 CNC machines. Need delivery to Pune urgently.",
        },
    )
    assert create_res.status_code == 201
    lead_id = create_res.json()["lead_id"]

    # 2. Call Analyze Endpoint
    analyze_res = client.post(f"/api/leads/{lead_id}/analyze")
    assert analyze_res.status_code == 200
    data = analyze_res.json()

    # 3. Assert AI Understanding Fields Persisted
    assert data["intent"] == "purchase"
    assert data["urgency"] == "high"
    assert data["product"] == "CNC machines"
    assert data["quantity"] == 10
    assert data["location"] == "Pune"
    assert data["ai_summary"] is not None
    assert data["recommended_action"] is not None
    assert data["response_draft"] is not None
    assert data["response_status"] == "draft"

    # 4. Assert PolicyEngine Deterministic Fields
    assert data["score"] in [93, 95]
    assert data["priority"] == "HOT"
    assert data["lifecycle_status"] == "analyzed"
    assert data["risk_status"] == "normal"
    assert data["at_risk_at"] is not None

    # 5. Assert Audit Event 'lead_analyzed' Recorded
    audit_res = client.get(f"/api/leads/{lead_id}/audit")
    assert audit_res.status_code == 200
    audit_actions = [e["action"] for e in audit_res.json()]
    assert "lead_analyzed" in audit_actions


def test_analyze_nonexistent_lead():
    res = client.post("/api/leads/nonexistent-id-123/analyze")
    assert res.status_code == 404
