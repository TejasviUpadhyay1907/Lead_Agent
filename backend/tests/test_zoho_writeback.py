from urllib.error import HTTPError

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.integrations import zoho_oauth, zoho_writeback
from app import zoho_writeback_worker
from app.api import deps


def _config():
    return {
        "refresh_token": "refresh-token",
        "accounts_url": "https://accounts.zoho.in",
        "client_id": "client-id",
        "client_secret": "client-secret",
        "outcome_writeback_enabled": True,
        "outcome_field_mapping": {
            "outcome": "LeadRescue_Outcome",
            "sales_value": "LeadRescue_Value",
            "sales_currency": "LeadRescue_Currency",
            "reason": "LeadRescue_Reason",
            "recorded_at": "LeadRescue_Recorded_At",
        },
    }


def test_build_outcome_fields_only_sends_configured_nonempty_fields():
    fields = zoho_writeback.build_outcome_fields(_config(), {
        "outcome": "won",
        "sales_value": "1200.50",
        "sales_currency": "INR",
        "reason": None,
        "recorded_at": "2026-10-10T12:00:00+00:00",
        "customer_email": "private@example.com",
    })
    assert fields == {
        "LeadRescue_Outcome": "won",
        "LeadRescue_Value": "1200.50",
        "LeadRescue_Currency": "INR",
        "LeadRescue_Reason": None,
        "LeadRescue_Recorded_At": "2026-10-10T12:00:00+00:00",
    }
    assert "customer_email" not in fields


def test_build_outcome_fields_requires_explicit_enablement():
    config = {**_config(), "outcome_writeback_enabled": False}
    with pytest.raises(zoho_writeback.ZohoWritebackError) as exc:
        zoho_writeback.build_outcome_fields(config, {"outcome": "won"})
    assert exc.value.code == "writeback_not_configured"
    assert not exc.value.retryable


def test_update_reads_current_version_then_puts_only_outcome_with_precondition(monkeypatch):
    config = _config()
    calls = []
    monkeypatch.setattr(zoho_writeback, "load_oauth_config", lambda: config)
    monkeypatch.setattr(zoho_writeback, "refresh_access_token", lambda _cfg: ("access-token", "https://www.zohoapis.in"))

    def request(url, _token, method, payload=None, modified_since=None):
        calls.append((url, method, payload, modified_since))
        if method == "GET":
            return {"data": [{"id": "record-123", "Modified_Time": "2026-10-10T12:00:00+05:30"}]}
        return {"data": [{"code": "SUCCESS"}]}

    monkeypatch.setattr(zoho_writeback, "_request_json", request)
    zoho_writeback.update_lead_outcome("record-123", {"LeadRescue_Outcome": "won"})

    assert calls[0][1] == "GET"
    assert calls[1][1] == "PUT"
    assert calls[1][3] == "2026-10-10T12:00:00+05:30"
    assert calls[1][2] == {"data": [{"id": "record-123", "LeadRescue_Outcome": "won"}]}


def test_provider_conflict_is_terminal_for_manual_reconciliation(monkeypatch):
    monkeypatch.setattr(
        zoho_writeback,
        "_urlopen_no_redirect",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(HTTPError("https://api.example", 412, "stale", {}, None)),
    )
    with pytest.raises(zoho_writeback.ZohoWritebackError) as exc:
        zoho_writeback._request_json("https://www.zohoapis.in/crm/v8/Leads", "access", "PUT", {"data": []})
    assert exc.value.code == "crm_record_changed"
    assert exc.value.retryable is False


def test_oauth_configuration_rejects_duplicate_or_unsafe_outcome_fields(monkeypatch):
    import json
    from fastapi import HTTPException

    monkeypatch.setattr(zoho_oauth.settings, "zoho_oauth_secret_arn", "secret-arn")
    config = {
        "client_id": "client-id",
        "client_secret": "client-secret",
        "accounts_url": "https://accounts.zoho.in",
        "redirect_uri": "https://api.example.com/integrations/v1/zoho/oauth/callback",
        "outcome_field_mapping": {"outcome": "LeadRescue_Outcome", "reason": "LeadRescue_Outcome"},
    }

    class SecretClient:
        def get_secret_value(self, **_kwargs):
            return {"SecretString": json.dumps(config)}

    monkeypatch.setattr(zoho_oauth, "_secrets_client", lambda: SecretClient())
    with pytest.raises(HTTPException) as exc:
        zoho_oauth.load_oauth_config()
    assert exc.value.status_code == 503

    config["outcome_field_mapping"] = {"outcome": "Lead_Status"}
    with pytest.raises(HTTPException) as reserved:
        zoho_oauth.load_oauth_config()
    assert reserved.value.status_code == 503


def test_sales_outcome_and_zoho_outbox_are_saved_together(monkeypatch):
    monkeypatch.setattr(zoho_oauth.settings, "zoho_oauth_secret_arn", "secret-arn")
    monkeypatch.setattr("app.api.leads.source_record_id_for_lead", lambda _lead_id: "zoho-record-123")
    monkeypatch.setattr("app.api.leads.load_oauth_config", lambda: _config())
    response = TestClient(app).post("/api/leads", json={
        "customer_name": "Outbox Integration Lead",
        "customer_email": "outbox-integration@example.com",
        "source": "website",
        "raw_message": "Please send a quote for equipment.",
    })
    assert response.status_code == 201
    lead_id = response.json()["lead_id"]

    result = TestClient(app).put(f"/api/leads/{lead_id}/outcome", json={
        "outcome": "won",
        "sales_value": "1200.50",
        "sales_currency": "INR",
    })

    assert result.status_code == 200
    saved = result.json()
    assert saved["crm_sync_status"] == "pending"
    assert saved["crm_sync_event_id"]
    outbox = next(item for item in deps.get_leads_repo()._memory_outbox if item["lead_id"] == lead_id)
    assert outbox["source_record_id"] == "zoho-record-123"
    assert outbox["fields"]["LeadRescue_Outcome"] == "won"
    assert outbox["fields"]["LeadRescue_Value"] == "1200.50"
    assert outbox["fields"]["LeadRescue_Currency"] == "INR"
    assert outbox["fields"]["LeadRescue_Recorded_At"] == saved["sales_outcome_at"]
    assert "customer_email" not in outbox["fields"]


def _stream_record(event_id="event-1", tenant_id="tenant-test"):
    return {
        "eventName": "INSERT",
        "dynamodb": {
            "SequenceNumber": "sequence-1",
            "NewImage": {
                "event_id": {"S": event_id},
                "tenant_id": {"S": tenant_id},
                "lead_id": {"S": "lead-1"},
                "tenant_lead_key": {"S": f"{tenant_id}#lead-1"},
                "source_record_id": {"S": "zoho-record-1"},
                "fields": {"M": {"LeadRescue_Outcome": {"S": "won"}}},
            },
        },
    }


def test_worker_returns_partial_failure_for_retryable_provider_errors(monkeypatch):
    class TestSettings:
        effective_tenant_id = "tenant-test"

    monkeypatch.setattr(zoho_writeback_worker, "settings", TestSettings())
    monkeypatch.setattr(zoho_writeback_worker, "_writeback_state", lambda _item: "current")
    monkeypatch.setattr(
        zoho_writeback_worker,
        "update_lead_outcome",
        lambda *_args: (_ for _ in ()).throw(zoho_writeback.ZohoWritebackError("provider_unavailable", retryable=True)),
    )
    response = zoho_writeback_worker.handler({"Records": [_stream_record()]}, None)
    assert response == {"batchItemFailures": [{"itemIdentifier": "sequence-1"}]}


def test_worker_marks_conflicts_and_audits_them_without_retrying(monkeypatch):
    statuses = []
    outbox = []
    audits = []

    class TestSettings:
        effective_tenant_id = "tenant-test"

    monkeypatch.setattr(zoho_writeback_worker, "settings", TestSettings())
    monkeypatch.setattr(zoho_writeback_worker, "_writeback_state", lambda _item: "current")
    monkeypatch.setattr(
        zoho_writeback_worker,
        "update_lead_outcome",
        lambda *_args: (_ for _ in ()).throw(zoho_writeback.ZohoWritebackError("crm_record_changed", retryable=False)),
    )
    monkeypatch.setattr(zoho_writeback_worker, "_set_lead_status", lambda _item, status, code=None: statuses.append((status, code)))
    monkeypatch.setattr(zoho_writeback_worker, "_mark_outbox", lambda _item, status, code=None: outbox.append((status, code)))
    monkeypatch.setattr(zoho_writeback_worker, "_record_audit", lambda _item, status, code=None: audits.append((status, code)))

    response = zoho_writeback_worker.handler({"Records": [_stream_record()]}, None)

    assert response == {"batchItemFailures": []}
    assert statuses == outbox == audits == [("conflict", "crm_record_changed")]


def test_worker_skips_outcome_event_superseded_by_a_newer_operator_update(monkeypatch):
    outbox = []
    audits = []

    class TestSettings:
        effective_tenant_id = "tenant-test"

    monkeypatch.setattr(zoho_writeback_worker, "settings", TestSettings())
    monkeypatch.setattr(zoho_writeback_worker, "_writeback_state", lambda _item: "superseded")
    monkeypatch.setattr(zoho_writeback_worker, "update_lead_outcome", lambda *_args: pytest.fail("stale CRM update attempted"))
    monkeypatch.setattr(zoho_writeback_worker, "_mark_outbox", lambda _item, status, _code=None: outbox.append(status))
    monkeypatch.setattr(zoho_writeback_worker, "_record_audit", lambda _item, status, _code=None: audits.append(status))

    response = zoho_writeback_worker.handler({"Records": [_stream_record()]}, None)

    assert response == {"batchItemFailures": []}
    assert outbox == ["superseded"]
    assert audits == ["superseded"]


def test_worker_blocks_pending_writeback_after_privacy_or_opt_out_hold(monkeypatch):
    statuses = []
    outbox = []
    audits = []

    class TestSettings:
        effective_tenant_id = "tenant-test"

    monkeypatch.setattr(zoho_writeback_worker, "settings", TestSettings())
    monkeypatch.setattr(zoho_writeback_worker, "_writeback_state", lambda _item: "blocked")
    monkeypatch.setattr(zoho_writeback_worker, "update_lead_outcome", lambda *_args: pytest.fail("held lead was written to CRM"))
    monkeypatch.setattr(zoho_writeback_worker, "_set_lead_status", lambda _item, status, code=None: statuses.append((status, code)))
    monkeypatch.setattr(zoho_writeback_worker, "_mark_outbox", lambda _item, status, code=None: outbox.append((status, code)))
    monkeypatch.setattr(zoho_writeback_worker, "_record_audit", lambda _item, status, code=None: audits.append((status, code)))

    response = zoho_writeback_worker.handler({"Records": [_stream_record()]}, None)

    assert response == {"batchItemFailures": []}
    assert statuses == outbox == audits == [("failed", "privacy_or_opt_out_hold")]
