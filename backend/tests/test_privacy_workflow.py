"""Regression coverage for the customer privacy intake and hold workflow."""

import pytest
import json
from fastapi.testclient import TestClient

from app.api.deps import _audit_repo, _leads_repo, _privacy_requests_repo
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_privacy_workflow_state():
    _leads_repo._memory_store.clear()
    _leads_repo._memory_suppressions.clear()
    _audit_repo._memory_store.clear()
    _privacy_requests_repo._memory_store.clear()
    yield
    _leads_repo._memory_store.clear()
    _leads_repo._memory_suppressions.clear()
    _audit_repo._memory_store.clear()
    _privacy_requests_repo._memory_store.clear()


def create_lead(message, email="privacy-customer@example.com"):
    response = client.post("/api/leads", json={
        "customer_name": "Privacy Customer",
        "customer_email": email,
        "source": "website",
        "raw_message": message,
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_access_request_holds_sales_flow_and_status_changes_are_audited():
    lead = create_lead("Send me my data")

    assert lead["privacy_hold"] is True
    assert lead["lifecycle_status"] == "new"
    assert lead["response_draft"] is None

    requests = client.get("/api/privacy/requests?status=open")
    assert requests.status_code == 200
    assert len(requests.json()) == 1
    request = requests.json()[0]
    assert request["lead_id"] == lead["lead_id"]
    assert request["request_type"] == "access"
    assert "customer_email" not in request

    analyze = client.post(f"/api/leads/{lead['lead_id']}/analyze")
    assert analyze.status_code == 409
    response_action = client.put(f"/api/leads/{lead['lead_id']}/response", json={"action": "approve"})
    assert response_action.status_code == 409
    rescue = client.post(f"/api/leads/{lead['lead_id']}/rescue")
    assert rescue.status_code == 200
    assert rescue.json() == {"rescued": False, "reason": "privacy_request_pending"}

    for target in ("identity_verification_required", "verified", "in_progress", "completed"):
        body = {"status": target}
        if target == "completed":
            body["resolution_code"] = "access_provided"
        update = client.put(f"/api/privacy/requests/{request['request_id']}/status", json=body)
        assert update.status_code == 200, update.text

    audit = client.get(f"/api/leads/{lead['lead_id']}/audit")
    assert audit.status_code == 200
    assert sum(event["action"] == "privacy_request_status_changed" for event in audit.json()) == 4
    persisted_lead = client.get(f"/api/leads/{lead['lead_id']}").json()
    assert persisted_lead["privacy_hold"] is True


def test_erasure_request_suppresses_future_matching_contact():
    lead = create_lead("Please delete my data", email="erase-me@example.com")

    assert lead["privacy_hold"] is True
    assert lead["lifecycle_status"] == "opted_out"

    new_lead = create_lead("I need a quote for a new order", email="erase-me@example.com")
    assert new_lead["lifecycle_status"] == "opted_out"
    assert new_lead["privacy_hold"] is False


def test_related_record_discovery_requires_verified_identity_and_paginates_without_pii():
    earlier = create_lead("A previous sales inquiry")
    request_lead = create_lead("Send me my data")
    request = client.get("/api/privacy/requests?status=open").json()[0]

    endpoint = f"/api/privacy/requests/{request['request_id']}/records?match=email&limit=1"
    denied = client.get(endpoint)
    assert denied.status_code == 409

    for target in ("identity_verification_required", "verified"):
        status_update = client.put(
            f"/api/privacy/requests/{request['request_id']}/status",
            json={"status": target},
        )
        assert status_update.status_code == 200, status_update.text

    first_page = client.get(endpoint)
    assert first_page.status_code == 200
    assert len(first_page.json()) == 1
    assert first_page.headers.get("X-Next-Cursor")
    assert "customer_email" not in first_page.json()[0]
    assert "raw_message" not in first_page.json()[0]

    second_page = client.get(endpoint + "&cursor=" + first_page.headers["X-Next-Cursor"])
    assert second_page.status_code == 200
    matching_ids = {first_page.json()[0]["lead_id"], second_page.json()[0]["lead_id"]}
    assert matching_ids == {earlier["lead_id"], request_lead["lead_id"]}

    audit = client.get(f"/api/leads/{request_lead['lead_id']}/audit").json()
    discovery_event = next(event for event in audit if event["action"] == "privacy_subject_records_discovered")
    assert discovery_event["details"]["match_count"] == 1
    assert discovery_event["details"]["matched_lead_ids"] == [first_page.json()[0]["lead_id"]]
    assert "customer_email" not in discovery_event["details"]


def test_access_record_export_requires_verified_request_and_matching_contact():
    first = create_lead("Previous inquiry", email="shared@example.com")
    request_lead = create_lead("Send me my data", email="shared@example.com")
    unrelated = create_lead("Unrelated inquiry", email="other@example.com")
    request = client.get("/api/privacy/requests?status=open").json()[0]
    endpoint = f"/api/privacy/requests/{request['request_id']}/records/{first['lead_id']}/export?match=email"

    unverified = client.get(endpoint)
    assert unverified.status_code == 409

    for target in ("identity_verification_required", "verified"):
        response = client.put(
            f"/api/privacy/requests/{request['request_id']}/status",
            json={"status": target},
        )
        assert response.status_code == 200

    mismatched = client.get(
        f"/api/privacy/requests/{request['request_id']}/records/{unrelated['lead_id']}/export?match=email"
    )
    assert mismatched.status_code == 404

    exported = client.get(endpoint)
    assert exported.status_code == 200
    assert exported.headers["cache-control"] == "private, no-store"
    payload = json.loads(exported.content)
    assert payload["lead"]["lead_id"] == first["lead_id"]
    assert payload["export_context"] == {
        "privacy_request_id": request["request_id"],
        "identifier_type": "email",
        "scope": "one_lead_record_and_its_local_history",
        "complete_subject_export": False,
        "limitation": "This export covers one LeadRescue lead matched by the selected stored identifier. It does not include other identifiers or external systems.",
    }
    events = client.get(f"/api/leads/{first['lead_id']}/audit").json()
    export_event = next(event for event in events if event["action"] == "privacy_subject_record_exported")
    assert export_event["details"]["privacy_request_id"] == request["request_id"]
    assert request_lead["lead_id"] != first["lead_id"]


def test_verified_access_request_downloads_a_bounded_bundle_for_one_identifier():
    first = create_lead("Previous inquiry", email="bundle@example.com")
    request_lead = create_lead("Send me my data", email="bundle@example.com")
    unrelated = create_lead("Different customer", email="unrelated@example.com")
    request = client.get("/api/privacy/requests?status=open").json()[0]
    endpoint = f"/api/privacy/requests/{request['request_id']}/export?match=email"

    unverified = client.get(endpoint)
    assert unverified.status_code == 409
    for target in ("identity_verification_required", "verified"):
        response = client.put(
            f"/api/privacy/requests/{request['request_id']}/status",
            json={"status": target},
        )
        assert response.status_code == 200

    response = client.get(endpoint)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert "attachment; filename=\"access-" in response.headers["content-disposition"]
    payload = json.loads(response.content)
    assert {item["lead"]["lead_id"] for item in payload["records"]} == {
        first["lead_id"], request_lead["lead_id"],
    }
    assert all(set(item) == {"lead", "followups", "audit_events", "whatsapp_messages"} for item in payload["records"])
    assert payload["export_context"]["complete_for_current_index_results"] is True
    assert payload["export_context"]["complete_subject_export"] is False
    assert "eventually_consistent" in payload["export_context"]["index_consistency"]
    assert unrelated["lead_id"] not in {item["lead"]["lead_id"] for item in payload["records"]}
    source_export = next(item for item in payload["records"] if item["lead"]["lead_id"] == request_lead["lead_id"])
    assert any(event["action"] == "privacy_subject_bundle_exported" for event in source_export["audit_events"])


def test_verified_access_bundle_refuses_partial_results_over_record_limit(monkeypatch):
    first = create_lead("Previous inquiry", email="large-bundle@example.com")
    request_lead = create_lead("Send me my data", email="large-bundle@example.com")
    request = client.get("/api/privacy/requests?status=open").json()[0]
    for target in ("identity_verification_required", "verified"):
        response = client.put(
            f"/api/privacy/requests/{request['request_id']}/status",
            json={"status": target},
        )
        assert response.status_code == 200

    monkeypatch.setattr("app.api.privacy.MAX_PRIVACY_BUNDLE_RECORDS", 1)
    response = client.get(f"/api/privacy/requests/{request['request_id']}/export?match=email")
    assert response.status_code == 413
    assert response.json()["detail"].startswith("More than 1 records match")
    events = client.get(f"/api/leads/{request_lead['lead_id']}/audit").json()
    assert not any(event["action"] == "privacy_subject_bundle_exported" for event in events)
    assert first["lead_id"] != request_lead["lead_id"]


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("How do I delete my data?", None),
        ("Please do not delete my data.", None),
        ("I want a copy of my data", "access"),
        ("Erase my personal information", "erasure"),
    ],
)
def test_privacy_phrase_detection_is_explicit_and_filters_negation(message, expected):
    from app.policy.guardrails import detect_privacy_request

    assert detect_privacy_request(message) == expected
