import hashlib
import hmac
import json
import time

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import webhooks
from app.main import app
from app.models.audit import AuditEvent
from app.models.lead import Lead


def _signed_headers(body: bytes, *, timestamp: str | None = None, provider: str = "generic", event_id: str = "event-123"):
    timestamp = timestamp or str(int(time.time()))
    canonical = timestamp.encode() + b"." + provider.encode() + b"." + event_id.encode() + b"." + body
    signature = hmac.new(b"test-secret", canonical, hashlib.sha256).hexdigest()
    return {
        "X-Webhook-Timestamp": timestamp,
        "X-Webhook-Provider": provider,
        "Idempotency-Key": event_id,
        "X-Webhook-Signature": f"sha256={signature}",
    }


def test_verify_signature_accepts_exact_signed_bytes(monkeypatch):
    body = b'{"message":"Need a quote"}'
    monkeypatch.setattr(webhooks, "_get_webhook_secret", lambda: "test-secret")
    headers = _signed_headers(body)

    webhooks._verify_signature(
        body,
        headers["X-Webhook-Timestamp"],
        headers["X-Webhook-Provider"],
        headers["Idempotency-Key"],
        headers["X-Webhook-Signature"],
    )


@pytest.mark.parametrize(
    "timestamp,provider,event_id,signature,expected_status",
    [
        (str(int(time.time()) - 600), "generic", "event-123", "sha256=" + "0" * 64, 401),
        (str(int(time.time())), "invalid provider", "event-123", "sha256=" + "0" * 64, 400),
        (str(int(time.time())), "generic", "bad key with spaces", "sha256=" + "0" * 64, 400),
        (str(int(time.time())), "generic", "event-123", "sha256=" + "0" * 64, 401),
    ],
)
def test_verify_signature_rejects_invalid_or_replayed_request(monkeypatch, timestamp, provider, event_id, signature, expected_status):
    monkeypatch.setattr(webhooks, "_get_webhook_secret", lambda: "test-secret")
    with pytest.raises(HTTPException) as exc:
        webhooks._verify_signature(b"{}", timestamp, provider, event_id, signature)
    assert exc.value.status_code == expected_status


def test_ingest_rejects_oversized_body_before_signature_work(monkeypatch):
    called = False

    def should_not_verify(*_args):
        nonlocal called
        called = True

    monkeypatch.setattr(webhooks, "_verify_signature", should_not_verify)
    client = TestClient(app)
    response = client.post(
        "/integrations/v1/leads",
        content=b"x" * (webhooks._MAX_BODY_BYTES + 1),
        headers={
            "X-Webhook-Timestamp": str(int(time.time())),
            "X-Webhook-Signature": "unused",
            "Idempotency-Key": "event-123",
        },
    )

    assert response.status_code == 413
    assert not called


@pytest.mark.parametrize(
    "body",
    [
        b'{"customer_name":"Asha","source":"website","message":"Need a quote","unexpected":true}',
        b'{"customer_name":"Asha","source":"unknown","message":"Need a quote"}',
        b'{"customer_name":"","source":"website","message":"Need a quote"}',
        b'{"customer_name":"   ","source":"website","message":"  "}',
    ],
)
def test_ingest_rejects_invalid_payload_without_persisting(monkeypatch, body):
    monkeypatch.setattr(webhooks, "_verify_signature", lambda *_args: None)
    persisted = False

    def should_not_persist(*_args):
        nonlocal persisted
        persisted = True

    monkeypatch.setattr(webhooks, "_create_or_return_duplicate", should_not_persist)
    client = TestClient(app)
    response = client.post(
        "/integrations/v1/leads",
        content=body,
        headers={
            "X-Webhook-Timestamp": str(int(time.time())),
            "X-Webhook-Signature": "sha256=" + "0" * 64,
            "Idempotency-Key": "event-123",
        },
    )

    assert response.status_code == 422
    assert not persisted


def test_ingest_verifies_and_maps_valid_request(monkeypatch):
    body = json.dumps({
        "customer_name": "Asha Rao",
        "customer_email": "asha@example.com",
        "customer_phone": "+91-9000000000",
        "source": "website",
        "message": "Need a quote for 20 units.",
    }, separators=(",", ":")).encode()
    verified = {}
    persisted = {}

    def record_verification(raw, timestamp, provider, event_id, signature):
        verified.update(body=raw, timestamp=timestamp, provider=provider, event_id=event_id, signature=signature)

    def record_persistence(lead, audit, event_key, provider, idempotency_digest, payload_digest):
        persisted.update(lead=lead, audit=audit, event_key=event_key, provider=provider,
                         idempotency_digest=idempotency_digest, payload_digest=payload_digest)
        return webhooks.JSONResponse(status_code=201, content={"accepted": True, "duplicate": False, "lead_id": lead.lead_id})

    monkeypatch.setattr(webhooks, "_verify_signature", record_verification)
    monkeypatch.setattr(webhooks, "_create_or_return_duplicate", record_persistence)
    client = TestClient(app)
    response = client.post(
        "/integrations/v1/leads",
        content=body,
        headers=_signed_headers(body, provider="crm-test", event_id="source-evt-1"),
    )

    assert response.status_code == 201
    assert verified["body"] == body
    assert verified["provider"] == "crm-test"
    assert verified["event_id"] == "source-evt-1"
    assert persisted["lead"].raw_message == "Need a quote for 20 units."
    assert persisted["audit"].tenant_id == persisted["lead"].tenant_id
    assert persisted["payload_digest"] == hashlib.sha256(body).hexdigest()


class _FakeTable:
    def __init__(self, name):
        self.name = name
        self.event = None

    def get_item(self, Key, **_kwargs):
        if self.name == "test-suppressions":
            marker = Key["suppression_key"]
            if marker in {"migration", "history"}:
                return {"Item": {"index_key_scheme": "hmac-sha256-v1", "index_key_id": "key-v1"}}
        if self.name == "test-events":
            return {"Item": self.event} if self.event else {}
        return {}


class _FakeDynamo:
    def __init__(self, *, fail_transaction=False, event=None):
        self.tables = {
            "test-suppressions": _FakeTable("test-suppressions"),
            "test-events": _FakeTable("test-events"),
        }
        self.tables["test-events"].event = event
        self.meta = type("Meta", (), {})()
        self.meta.client = self
        self.fail_transaction = fail_transaction
        self.transact_items = None

    def Table(self, name):
        return self.tables[name]

    def transact_write_items(self, *, TransactItems):
        self.transact_items = TransactItems
        if self.fail_transaction:
            raise ClientError({"Error": {"Code": "TransactionCanceledException", "Message": "condition failed"}}, "TransactWriteItems")


def _patch_fake_dynamo(monkeypatch, fake):
    monkeypatch.setattr(webhooks, "get_boto3_dynamodb_resource", lambda: fake)
    monkeypatch.setattr(webhooks, "require_customer_index_key", lambda: "key-v1")
    monkeypatch.setattr(webhooks, "migration_marker_key", lambda _tenant: "migration")
    monkeypatch.setattr(webhooks, "history_index_marker_key", lambda _tenant: "history")
    monkeypatch.setattr(webhooks, "suppression_keys", lambda *_args: [])

    class TestSettings:
        effective_tenant_id = "tenant-test"
        customer_suppressions_table = "test-suppressions"
        processed_events_table = "test-events"
        leads_table = "test-leads"
        audit_table = "test-audit"

    monkeypatch.setattr(webhooks, "settings", TestSettings())


def test_persistence_commits_lead_audit_and_dedupe_marker_together(monkeypatch):
    fake = _FakeDynamo()
    _patch_fake_dynamo(monkeypatch, fake)
    lead = Lead(customer_name="Asha Rao", source="website", raw_message="Need a quote", tenant_id="tenant-test")
    audit = AuditEvent(lead_id=lead.lead_id, tenant_id="tenant-test", tenant_lead_id=f"tenant-test#{lead.lead_id}", action="lead_received", actor="integration:generic")

    response = webhooks._create_or_return_duplicate(lead, audit, "tenant-test#event", "generic", "event-digest", "payload-digest")

    assert response.status_code == 201
    assert len(fake.transact_items) == 3
    assert {next(iter(item)) for item in fake.transact_items} == {"Put"}
    assert [item["Put"]["TableName"] for item in fake.transact_items] == ["test-leads", "test-audit", "test-events"]


@pytest.mark.parametrize(
    "stored_digest,expected_status",
    [("payload-digest", 200), ("different-payload", 409)],
)
def test_duplicate_event_returns_original_lead_or_rejects_changed_payload(monkeypatch, stored_digest, expected_status):
    existing = {
        "event_key": "tenant-test#event",
        "tenant_id": "tenant-test",
        "provider": "generic",
        "payload_digest": stored_digest,
        "lead_id": "existing-lead",
    }
    fake = _FakeDynamo(fail_transaction=True, event=existing)
    _patch_fake_dynamo(monkeypatch, fake)
    lead = Lead(customer_name="Asha Rao", source="website", raw_message="Need a quote", tenant_id="tenant-test")
    audit = AuditEvent(lead_id=lead.lead_id, tenant_id="tenant-test", tenant_lead_id=f"tenant-test#{lead.lead_id}", action="lead_received", actor="integration:generic")

    if expected_status == 409:
        with pytest.raises(HTTPException) as exc:
            webhooks._create_or_return_duplicate(lead, audit, "tenant-test#event", "generic", "event-digest", "payload-digest")
        assert exc.value.status_code == 409
    else:
        response = webhooks._create_or_return_duplicate(lead, audit, "tenant-test#event", "generic", "event-digest", "payload-digest")
        assert response.status_code == expected_status
        assert json.loads(response.body)["lead_id"] == "existing-lead"
