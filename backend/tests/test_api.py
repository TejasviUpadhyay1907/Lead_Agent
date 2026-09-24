"""
LeadRescue AI — API Integration Tests
Tests all Phase 2 backend REST API endpoints using TestClient.
"""

from datetime import datetime, timedelta, timezone

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


def test_common_opt_out_variants_are_enforced_at_lead_intake():
    for index, message in enumerate((
        "Please don’t message me again.",
        "Do not contact us.",
        "No more emails, please.",
        "Please opt me out of promotions.",
    )):
        response = client.post("/api/leads", json={
            "customer_name": f"Opt-out Contact {index}",
            "customer_email": f"opt-out-intake-{index}@example.com",
            "source": "website",
            "raw_message": message,
        })
        assert response.status_code == 201
        assert response.json()["lifecycle_status"] == "opted_out"


def test_question_about_opt_out_policy_does_not_suppress_contact():
    response = client.post("/api/leads", json={
        "customer_name": "Policy Question Contact",
        "customer_email": "policy-question@example.com",
        "source": "website",
        "raw_message": "Can you explain your opt-out policy?",
    })

    assert response.status_code == 201
    assert response.json()["lifecycle_status"] == "new"


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


def test_sales_outcome_records_confirmed_value_and_audit_event():
    created = client.post("/api/leads", json={
        "customer_name": "Outcome Capture Contact",
        "customer_email": "outcome-capture@example.com",
        "source": "website",
        "raw_message": "Please send product details.",
    })
    assert created.status_code == 201
    lead_id = created.json()["lead_id"]

    response = client.put(f"/api/leads/{lead_id}/outcome", json={
        "outcome": "won",
        "sales_value": "125000.50",
        "sales_currency": "INR",
        "reason": "Converted after a technical consultation.",
    })

    assert response.status_code == 200
    data = response.json()
    assert data["sales_outcome"] == "won"
    assert data["sales_value"] == "125000.50"
    assert data["sales_currency"] == "INR"
    assert data["sales_outcome_reason"] == "Converted after a technical consultation."
    assert data["sales_outcome_at"]
    assert data["lifecycle_status"] == "resolved"

    audit = client.get(f"/api/leads/{lead_id}/audit")
    assert audit.status_code == 200
    event = next(item for item in audit.json() if item["action"] == "sales_outcome_recorded")
    assert event["details"]["source"] == "operator_entered"
    assert event["details"]["sales_value"] == "125000.50"


def test_sales_outcome_rejects_missing_loss_reason_and_unpaired_currency():
    missing_reason = client.put("/api/leads/does-not-matter/outcome", json={"outcome": "lost"})
    assert missing_reason.status_code == 422

    unpaired_currency = client.put("/api/leads/does-not-matter/outcome", json={
        "outcome": "won", "sales_currency": "INR",
    })
    assert unpaired_currency.status_code == 422

    value_for_loss = client.put("/api/leads/does-not-matter/outcome", json={
        "outcome": "lost", "reason": "Budget unavailable", "sales_value": "200", "sales_currency": "INR",
    })
    assert value_for_loss.status_code == 422


def test_sales_outcome_respects_privacy_and_opt_out_guards():
    privacy_lead = client.post("/api/leads", json={
        "customer_name": "Privacy Outcome Contact",
        "customer_email": "privacy-outcome@example.com",
        "source": "website",
        "raw_message": "I want a copy of my data.",
    })
    assert privacy_lead.status_code == 201
    held = client.put(f"/api/leads/{privacy_lead.json()['lead_id']}/outcome", json={"outcome": "won"})
    assert held.status_code == 409

    opted_out_lead = client.post("/api/leads", json={
        "customer_name": "Suppressed Outcome Contact",
        "customer_email": "suppressed-outcome@example.com",
        "source": "website",
        "raw_message": "Please stop contacting me.",
    })
    assert opted_out_lead.status_code == 201
    suppressed = client.put(f"/api/leads/{opted_out_lead.json()['lead_id']}/outcome", json={"outcome": "won"})
    assert suppressed.status_code == 409


def test_outcome_report_is_bounded_and_returns_explicit_cohort_and_consistency():
    today = datetime.now(timezone.utc).date().isoformat()
    response = client.get(f"/api/reports/outcomes?start_date={today}&end_date={today}")

    assert response.status_code == 200
    report = response.json()
    assert report["start_date"] == today
    assert report["end_date"] == today
    assert report["cohort"] == "lead_created_at_utc"
    assert report["consistency"] == "eventually_consistent"
    assert set(report["counts"]) == {"total", "won", "lost", "disqualified", "open"}

    future = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    invalid = client.get(f"/api/reports/outcomes?start_date={today}&end_date={future}")
    assert invalid.status_code == 422
