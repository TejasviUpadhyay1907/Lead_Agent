"""
LeadRescue AI — Integration Tests for POST /api/leads/{id}/analyze Endpoint
"""

from fastapi.testclient import TestClient
from app.main import app
from app.api.deps import get_audit_repo, get_config_repo, get_followups_repo, get_leads_repo
from app.api.leads import analyze_lead_core
from fastapi import HTTPException
import pytest

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


def test_opted_out_lead_is_blocked_before_sync_or_queued_analysis(monkeypatch):
    created = client.post("/api/leads", json={
        "customer_name": "Opted Out Analysis Contact",
        "customer_email": "opted-out-analysis@example.com",
        "source": "website",
        "raw_message": "Please do not message me again.",
    })
    assert created.status_code == 201
    lead_id = created.json()["lead_id"]
    assert created.json()["lifecycle_status"] == "opted_out"

    sync = client.post(f"/api/leads/{lead_id}/analyze")
    queued = client.post(
        f"/api/leads/{lead_id}/analysis-jobs",
        headers={"Idempotency-Key": "optout-analysis-block-001"},
    )

    assert sync.status_code == 409
    assert queued.status_code == 409
    assert "opted out" in sync.json()["detail"].lower()
    assert "opted out" in queued.json()["detail"].lower()

    monkeypatch.setattr(
        "app.api.leads.LeadRescueAgent.analyze_lead",
        lambda *_args: pytest.fail("Opted-out inquiry must not be sent to the model"),
    )
    with pytest.raises(HTTPException) as exc_info:
        analyze_lead_core(
            lead_id,
            {"sub": "worker-test"},
            get_leads_repo(),
            get_followups_repo(),
            get_audit_repo(),
            get_config_repo(),
            analysis_job_id="already-queued-job",
        )
    assert exc_info.value.status_code == 409


def test_completed_analysis_job_redelivery_is_idempotent(monkeypatch):
    created = client.post("/api/leads", json={
        "customer_name": "Job Redelivery Contact",
        "customer_email": "job-redelivery@example.com",
        "source": "website",
        "raw_message": "Please send product information.",
    })
    assert created.status_code == 201
    lead_id = created.json()["lead_id"]
    lead_repo = get_leads_repo()
    lead = lead_repo.get_by_id(lead_id)
    lead.last_analysis_job_id = "completed-job-identifier"
    lead_repo.save(lead)

    monkeypatch.setattr(
        "app.api.leads.LeadRescueAgent.analyze_lead",
        lambda *_args: pytest.fail("A completed job redelivery must not repeat inference"),
    )
    result = analyze_lead_core(
        lead_id,
        {"sub": "worker-test"},
        lead_repo,
        get_followups_repo(),
        get_audit_repo(),
        get_config_repo(),
        analysis_job_id="completed-job-identifier",
    )

    assert result.lead_id == lead_id
    assert result.last_analysis_job_id == "completed-job-identifier"
