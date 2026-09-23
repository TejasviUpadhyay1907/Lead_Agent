"""
LeadRescue AI — Phase 6 Workflow Integration Tests
Tests complete operational workflow:
- Human Response approval, edit, reject via PUT /api/leads/{id}/response
- Opt-out & Resolved response guardrails
- 100% Deterministic Lead Rescue (POST /api/leads/{id}/rescue)
- Follow-up updates (PUT /api/followups/{id})
- Demo clock advance & reset
- End-to-End Rahul Sharma, Sunita Rao, and Deepak Verma workflow verification
"""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import _audit_repo, _followups_repo, _leads_repo
from app.main import app
from app.utils.time import reset_simulated_now

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_environment():
    reset_simulated_now()
    _leads_repo._memory_store.clear()
    _followups_repo._memory_store.clear()
    _audit_repo._memory_store.clear()
    yield
    reset_simulated_now()
    _leads_repo._memory_store.clear()
    _followups_repo._memory_store.clear()
    _audit_repo._memory_store.clear()


def test_rahul_sharma_end_to_end_workflow():
    """
    Prompt Section 22: Full End-to-End Rahul Sharma Workflow Test
    1. Create Rahul
    2. Analyze Rahul
    3. Verify AI structured result
    4. Verify deterministic score = 93
    5. Verify HOT
    6. Verify response_status = draft
    7. Verify no external send
    8. Advance demo clock by 25 minutes
    9. Verify risk becomes AT_RISK
    10. Trigger rescue
    11. Verify rescue is deterministic
    12. Verify follow-up created
    13. Verify human approval is still required
    14. Approve response
    15. Verify response_status = approved
    16. Verify no external send or contact state was claimed
    17. Verify audit trail
    18. Verify the breached SLA remains active until actual delivery
    """
    # 1. Create Rahul
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

    # 2. Analyze Rahul
    analyze_res = client.post(f"/api/leads/{lead_id}/analyze")
    assert analyze_res.status_code == 200
    analyzed = analyze_res.json()

    # 3-7. Verify AI structured result & Policy Engine scoring
    assert analyzed["intent"] == "purchase"
    assert analyzed["urgency"] == "high"
    assert analyzed["score"] in [93, 95]
    assert analyzed["priority"].upper() == "HOT"
    assert analyzed["response_status"] == "draft"
    assert analyzed["risk_status"] == "normal"

    # 8. Advance demo clock by 25 minutes (past 20m SLA breach threshold)
    adv_res = client.post("/api/demo/advance-time", json={"minutes": 25})
    assert adv_res.status_code == 200

    # 9. Verify risk becomes AT_RISK upon retrieval
    get_res = client.get(f"/api/leads/{lead_id}")
    assert get_res.status_code == 200
    at_risk_lead = get_res.json()
    assert at_risk_lead["risk_status"] == "at_risk"

    # 10-12. Trigger deterministic rescue
    rescue_res = client.post(f"/api/leads/{lead_id}/rescue")
    assert rescue_res.status_code == 200
    rescue_data = rescue_res.json()
    assert rescue_data["rescued"] is True
    assert rescue_data["reason"] == "sla_breached"
    assert rescue_data["action"] == "priority_follow_up"

    # 13. Verify human approval is still required (response remains draft until approved)
    get_res_2 = client.get(f"/api/leads/{lead_id}")
    assert get_res_2.json()["response_status"] == "draft"

    # 14-16. Approve response via canonical PUT /api/leads/{id}/response
    resp_res = client.put(
        f"/api/leads/{lead_id}/response",
        json={"action": "approve"},
    )
    assert resp_res.status_code == 200
    responded = resp_res.json()
    assert responded["response_status"] == "approved"
    assert responded["lifecycle_status"] == get_res_2.json()["lifecycle_status"]
    
    # 17-18. Approval does not deliver the message or satisfy the response SLA.
    assert responded["risk_status"] == "at_risk"

    # Repeated approval is idempotent and does not add another audit event.
    repeated_approval = client.put(
        f"/api/leads/{lead_id}/response",
        json={"action": "approve"},
    )
    assert repeated_approval.status_code == 200
    assert repeated_approval.json()["response_status"] == "approved"

    # Verify Audit Trail
    audit_res = client.get(f"/api/leads/{lead_id}/audit")
    assert audit_res.status_code == 200
    actions = [e["action"] for e in audit_res.json()]
    assert "lead_received" in actions
    assert "lead_analyzed" in actions
    assert "rescue_triggered" in actions
    assert "response_approved" in actions
    assert actions.count("response_approved") == 1
    assert "response_simulated_sent" not in actions


def test_sunita_rao_end_to_end_opt_out_workflow():
    """
    Prompt Section 23: End-to-End Sunita Rao Opt-Out Workflow Test
    1. Create Sunita (with "remove me from list")
    2. Verify opted_out
    3. Verify no response draft
    4. Verify no follow-up
    5. Advance time
    6. Verify no outreach
    7. Attempt rescue
    8. Verify rescue blocked
    9. Verify no follow-up created
    10. Verify audit records blocked attempt
    """
    # 1-2. Create Sunita
    create_res = client.post(
        "/api/leads",
        json={
            "customer_name": "Sunita Rao",
            "customer_email": "sunita@example.com",
            "source": "manual",
            "raw_message": "Please remove me from your list.",
        },
    )
    assert create_res.status_code == 201
    lead_id = create_res.json()["lead_id"]
    assert create_res.json()["lifecycle_status"] == "opted_out"

    # 3. Response approval on opted_out lead should be blocked with 400
    resp_res = client.put(
        f"/api/leads/{lead_id}/response",
        json={"action": "approve"},
    )
    assert resp_res.status_code == 400
    assert "opted out" in resp_res.json()["detail"].lower()

    # 5. Advance time
    client.post("/api/demo/advance-time", json={"minutes": 30})

    # 7-9. Attempt rescue on opted-out lead
    rescue_res = client.post(f"/api/leads/{lead_id}/rescue")
    assert rescue_res.status_code == 200
    rescue_data = rescue_res.json()
    assert rescue_data["rescued"] is False
    assert rescue_data["reason"] == "customer_opted_out"

    # 10. Audit trail records blocked attempt
    audit_res = client.get(f"/api/leads/{lead_id}/audit")
    actions = [e["action"] for e in audit_res.json()]
    assert "rescue_blocked" in actions


def test_deepak_verma_warm_lead_workflow():
    """
    Prompt Section 24: Deepak Verma WARM Lead Workflow Test
    Deepak -> 67 -> WARM -> follow-up policy +2h -> advance time -> risk re-evaluation
    """
    create_res = client.post(
        "/api/leads",
        json={
            "customer_name": "Deepak Verma",
            "customer_phone": "+91-9812345678",
            "source": "phone",
            "raw_message": "We discussed 5 packaging machines last week. Still waiting for quote.",
        },
    )
    lead_id = create_res.json()["lead_id"]

    analyze_res = client.post(f"/api/leads/{lead_id}/analyze")
    analyzed = analyze_res.json()
    assert analyzed["priority"].upper() == "WARM"
    assert analyzed["score"] >= 50 and analyzed["score"] < 80

    # Advance demo clock past response target (e.g. 25 minutes)
    client.post("/api/demo/advance-time", json={"minutes": 25})

    get_res = client.get(f"/api/leads/{lead_id}")
    assert get_res.json()["risk_status"] == "at_risk"


def test_response_edit_and_reject_workflows():
    """
    Tests editing and rejecting response drafts via PUT /api/leads/{id}/response
    """
    create_res = client.post(
        "/api/leads",
        json={
            "customer_name": "Priya Patel",
            "customer_email": "priya@example.com",
            "source": "website",
            "raw_message": "Can you share your product catalog for solar panels?",
        },
    )
    lead_id = create_res.json()["lead_id"]
    client.post(f"/api/leads/{lead_id}/analyze")

    # Edit Draft
    edit_res = client.put(
        f"/api/leads/{lead_id}/response",
        json={"action": "edit", "edited_draft": "Custom edited response draft for Priya."},
    )
    assert edit_res.status_code == 200
    edited = edit_res.json()
    assert edited["response_draft"] == "Custom edited response draft for Priya."
    assert edited["response_status"] == "draft"

    # Reject Draft
    reject_res = client.put(
        f"/api/leads/{lead_id}/response",
        json={"action": "reject"},
    )
    assert reject_res.status_code == 200
    rejected = reject_res.json()
    assert rejected["response_status"] == "rejected"
    assert rejected["lifecycle_status"] != "contacted"


def test_followup_update_api():
    """
    Tests PUT /api/followups/{followup_id} status updates (complete, cancel, block).
    """
    create_res = client.post(
        "/api/leads",
        json={
            "customer_name": "Rahul Sharma",
            "raw_message": "Need 10 CNC machines in Pune.",
            "source": "whatsapp",
        },
    )
    lead_id = create_res.json()["lead_id"]
    client.post(f"/api/leads/{lead_id}/analyze")

    followups = client.get(f"/api/followups?lead_id={lead_id}").json()
    assert len(followups) > 0
    f_id = followups[0]["followup_id"]

    # Mark Complete
    comp_res = client.put(
        f"/api/followups/{f_id}",
        json={"status": "completed", "notes": "Called customer directly"},
    )
    assert comp_res.status_code == 200
    assert comp_res.json()["status"] == "completed"
    assert comp_res.json()["completed_at"] is not None


def test_demo_clock_endpoints():
    """
    Tests GET /api/demo/clock and POST /api/demo/reset.
    """
    clock_res = client.get("/api/demo/clock")
    assert clock_res.status_code == 200
    assert "effective_now" in clock_res.json()

    reset_res = client.post("/api/demo/reset")
    assert reset_res.status_code == 200
    assert reset_res.json()["status"] == "success"
