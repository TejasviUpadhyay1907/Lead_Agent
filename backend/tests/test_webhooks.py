import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import webhooks
from app.integrations import persistence as integration_persistence
from app.integrations import zoho
from app.main import app
from app.models.audit import AuditEvent
from app.models.lead import Lead
from app.models.enums import IntentEnum, LifecycleStatusEnum, PriorityEnum, ResponseStatusEnum, SalesOutcomeEnum, UrgencyEnum


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


def test_zoho_webhook_token_uses_constant_time_secret_comparison(monkeypatch):
    monkeypatch.setattr(webhooks, "_get_zoho_webhook_secret", lambda: "t" * 40)
    webhooks._verify_zoho_token("t" * 40)
    with pytest.raises(HTTPException) as exc:
        webhooks._verify_zoho_token("x" * 40)
    assert exc.value.status_code == 401


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

    def record_persistence(lead, audit, event_key, provider, idempotency_digest, payload_digest, privacy_request=None):
        persisted.update(lead=lead, audit=audit, event_key=event_key, provider=provider,
                         idempotency_digest=idempotency_digest, payload_digest=payload_digest,
                         privacy_request=privacy_request)
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
    assert persisted["privacy_request"] is None


def test_zoho_ingest_authenticates_maps_and_uses_permanent_record_dedupe(monkeypatch):
    body = json.dumps({
        "record_id": "5725767000000123456",
        "customer_name": "Asha Rao",
        "customer_email": "asha@example.com",
        "customer_phone": "+91-9000000000",
        "source": "website",
        "message": "Please send a quote for 20 units.",
        "modified_at": datetime.now(timezone.utc).isoformat(),
    }).encode()
    monkeypatch.setattr(webhooks, "_verify_zoho_token", lambda token: None)
    persisted = {}

    def record_persistence(*args, **kwargs):
        persisted["args"] = args
        persisted["kwargs"] = kwargs
        return webhooks.JSONResponse(status_code=201, content={"accepted": True, "duplicate": False, "lead_id": args[0].lead_id})

    monkeypatch.setattr(webhooks, "_create_or_return_duplicate", record_persistence)
    response = TestClient(app).post(
        "/integrations/v1/zoho/leads",
        content=body,
        headers={"Content-Type": "application/json", "X-LeadRescue-Token": "test-token"},
    )

    assert response.status_code == 201
    lead, audit, event_key, provider, event_digest, payload_digest, _privacy = persisted["args"]
    assert lead.customer_name == "Asha Rao"
    assert lead.raw_message == "Please send a quote for 20 units."
    assert provider == "zoho-crm"
    assert event_key.endswith(event_digest)
    assert audit.actor == "integration:zoho-crm"
    assert payload_digest == hashlib.sha256(webhooks.InboundLead(
        customer_name="Asha Rao",
        customer_email="asha@example.com",
        customer_phone="+91-9000000000",
        source="website",
        message="Please send a quote for 20 units.",
    ).model_dump_json().encode()).hexdigest()
    assert persisted["kwargs"] == {
        "permanent_idempotency": True,
        "source_modified_at": webhooks.ZohoLeadWebhook.model_validate_json(body).modified_at.isoformat(),
        "source_record_id": "5725767000000123456",
    }


def test_zoho_update_snapshot_schema_requires_complete_contact_fields_and_zoned_time():
    baseline = {
        "record_id": "5725767000000123456",
        "customer_name": "Asha Rao",
        "customer_email": None,
        "customer_phone": "+91-9000000000",
        "source": "website",
        "message": "Need a quote",
        "modified_at": datetime.now(timezone.utc).isoformat(),
    }
    parsed = webhooks.ZohoLeadUpdateWebhook.model_validate(baseline)
    assert parsed.customer_email is None
    assert parsed.modified_at.tzinfo is not None

    missing_contact = {**baseline}
    del missing_contact["customer_email"]
    with pytest.raises(ValueError, match="must be present"):
        webhooks.ZohoLeadUpdateWebhook.model_validate(missing_contact)

    naive_time = {**baseline, "modified_at": "2026-10-10T12:00:00"}
    with pytest.raises(ValueError, match="timezone offset"):
        webhooks.ZohoLeadUpdateWebhook.model_validate(naive_time)

    future_time = {**baseline, "modified_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()}
    with pytest.raises(ValueError, match="cannot be in the future"):
        webhooks.ZohoLeadUpdateWebhook.model_validate(future_time)


def test_zoho_update_route_authenticates_and_hashes_normalized_snapshot(monkeypatch):
    body = {
        "record_id": "5725767000000123456",
        "customer_name": "Asha Rao",
        "customer_email": "asha@example.com",
        "customer_phone": "+91-9000000000",
        "source": "website",
        "message": "Need a quote",
        "modified_at": datetime.now(timezone.utc).isoformat(),
    }
    verified = []
    submitted = {}
    monkeypatch.setattr(webhooks, "_verify_zoho_token", lambda token: verified.append(token))

    def apply_snapshot(payload, payload_digest):
        submitted["payload"] = payload
        submitted["digest"] = payload_digest
        return webhooks.JSONResponse(status_code=200, content={"accepted": True})

    monkeypatch.setattr(webhooks, "apply_lead_snapshot", apply_snapshot)
    response = TestClient(app).post(
        "/integrations/v1/zoho/leads/updates",
        json=body,
        headers={"X-LeadRescue-Token": "test-token"},
    )

    assert response.status_code == 200
    assert verified == ["test-token"]
    assert submitted["payload"].record_id == body["record_id"]
    expected = webhooks.InboundLead(
        customer_name=body["customer_name"],
        customer_email=body["customer_email"],
        customer_phone=body["customer_phone"],
        source=body["source"],
        message=body["message"],
    )
    assert submitted["digest"] == hashlib.sha256(expected.model_dump_json().encode("utf-8")).hexdigest()


class _FakeZohoTable:
    def __init__(self, *, item=None):
        self.item = item

    def get_item(self, Key, **_kwargs):
        key = next(iter(Key.values()))
        if key in {"migration", "history"}:
            return {"Item": {"index_key_scheme": "hmac-sha256-v1", "index_key_id": "key-v1"}}
        return {"Item": self.item} if self.item else {}


class _FakeZohoDynamo:
    def __init__(self, event, lead, *, fail_transaction=False):
        self.tables = {
            "test-events": _FakeZohoTable(item=event),
            "test-leads": _FakeZohoTable(item=lead),
            "test-suppressions": _FakeZohoTable(),
        }
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


def _patch_zoho_update_dynamo(monkeypatch, fake):
    monkeypatch.setattr(zoho, "get_boto3_dynamodb_resource", lambda: fake)
    monkeypatch.setattr(zoho, "require_customer_index_key", lambda: "key-v1")
    monkeypatch.setattr(zoho, "migration_marker_key", lambda _tenant: "migration")
    monkeypatch.setattr(zoho, "history_index_marker_key", lambda _tenant: "history")
    monkeypatch.setattr(zoho, "suppression_keys", lambda *_args: ["email#keyed", "phone#keyed"])

    class TestSettings:
        effective_tenant_id = "tenant-test"
        customer_suppressions_table = "test-suppressions"
        processed_events_table = "test-events"
        leads_table = "test-leads"
        audit_table = "test-audit"
        privacy_requests_table = "test-privacy"

    monkeypatch.setattr(zoho, "settings", TestSettings())
    monkeypatch.setattr(integration_persistence, "settings", TestSettings())
    monkeypatch.setattr(integration_persistence, "suppression_keys", lambda *_args: ["email#keyed", "phone#keyed"])


def test_zoho_newer_snapshot_updates_crm_fields_invalidates_stale_ai_and_preserves_operator_state(monkeypatch):
    now = datetime.now(timezone.utc)
    lead = Lead(
        lead_id="local-lead",
        tenant_id="tenant-test",
        customer_name="Asha Rao",
        customer_email="asha@example.com",
        customer_phone="+91-9000000000",
        source="website",
        raw_message="Need a quote",
        intent=IntentEnum.PURCHASE,
        urgency=UrgencyEnum.HIGH,
        ai_summary="Old summary",
        response_draft="Old draft",
        score=90,
        priority=PriorityEnum.HOT,
        lifecycle_status=LifecycleStatusEnum.CONTACTED,
        response_status=ResponseStatusEnum.APPROVED,
        approved_draft_sha256="a" * 64,
        approval_attested_at=now.isoformat(),
        approval_attested_by="operator-1",
        sales_outcome=SalesOutcomeEnum.WON,
    )
    prior_source_time = (now - timedelta(minutes=2)).isoformat()
    event_digest = hashlib.sha256(b"zoho-crm:5725767000000123456").hexdigest()
    event = {
        "event_key": f"tenant-test#{event_digest}",
        "tenant_id": "tenant-test",
        "provider": "zoho-crm",
        "lead_id": lead.lead_id,
        "source_modified_at": prior_source_time,
        "payload_digest": "old-digest",
    }
    fake = _FakeZohoDynamo(event, lead.model_dump())
    _patch_zoho_update_dynamo(monkeypatch, fake)
    payload = webhooks.ZohoLeadUpdateWebhook.model_validate({
        "record_id": "5725767000000123456",
        "customer_name": "Asha Rao Updated",
        "customer_email": "asha.new@example.com",
        "customer_phone": "+91-9111111111",
        "source": "email",
        "message": "Please quote 30 units",
        "modified_at": (now - timedelta(minutes=1)).isoformat(),
    })

    snapshot = webhooks.InboundLead(
        customer_name=payload.customer_name,
        customer_email=payload.customer_email,
        customer_phone=payload.customer_phone,
        source=payload.source,
        message=payload.message,
    )
    payload_digest = hashlib.sha256(snapshot.model_dump_json().encode("utf-8")).hexdigest()
    response = zoho.apply_lead_snapshot(payload, payload_digest)
    assert response.status_code == 200
    body = json.loads(response.body)
    assert body["updated"] is True
    assert set(body["changed_fields"]) == {"customer_name", "customer_email", "customer_phone", "source", "raw_message"}
    assert len(fake.transact_items) == 5
    updated_item = fake.transact_items[0]["Put"]["Item"]
    assert updated_item["customer_name"]["S"] == "Asha Rao Updated"
    assert updated_item["lifecycle_status"]["S"] == "contacted"
    assert updated_item["sales_outcome"]["S"] == "won"
    assert updated_item["response_draft"]["NULL"] is True
    assert updated_item["approved_draft_sha256"]["NULL"] is True
    assert updated_item["whatsapp_consent"]["NULL"] is True
    assert updated_item["score"]["NULL"] is True
    assert fake.transact_items[2]["Update"]["UpdateExpression"].startswith("SET source_modified_at")


def test_zoho_update_rejects_legacy_binding_and_ignores_stale_snapshot(monkeypatch):
    now = datetime.now(timezone.utc)
    lead = Lead(lead_id="local-lead", tenant_id="tenant-test", customer_name="Asha", source="website", raw_message="Quote")
    event_digest = hashlib.sha256(b"zoho-crm:record-1").hexdigest()
    event = {
        "event_key": f"tenant-test#{event_digest}",
        "tenant_id": "tenant-test",
        "provider": "zoho-crm",
        "lead_id": lead.lead_id,
        "source_modified_at": (now - timedelta(minutes=1)).isoformat(),
        "payload_digest": "old-digest",
    }
    payload = webhooks.ZohoLeadUpdateWebhook.model_validate({
        "record_id": "record-1",
        "customer_name": "Asha Older",
        "customer_email": None,
        "customer_phone": None,
        "source": "website",
        "message": "Old snapshot",
        "modified_at": (now - timedelta(minutes=2)).isoformat(),
    })
    fake = _FakeZohoDynamo(event, lead.model_dump())
    _patch_zoho_update_dynamo(monkeypatch, fake)
    snapshot = webhooks.InboundLead(
        customer_name=payload.customer_name,
        customer_email=payload.customer_email,
        customer_phone=payload.customer_phone,
        source=payload.source,
        message=payload.message,
    )
    payload_digest = hashlib.sha256(snapshot.model_dump_json().encode("utf-8")).hexdigest()
    response = zoho.apply_lead_snapshot(payload, payload_digest)
    assert response.status_code == 200
    assert json.loads(response.body)["stale"] is True
    assert fake.transact_items is None

    del event["source_modified_at"]
    with pytest.raises(HTTPException) as exc:
        zoho.apply_lead_snapshot(payload, payload_digest)
    assert exc.value.status_code == 409


def test_zoho_ingest_rejects_auth_and_incomplete_mapped_records(monkeypatch):
    monkeypatch.setattr(webhooks, "_verify_zoho_token", lambda _token: (_ for _ in ()).throw(HTTPException(status_code=401)))
    client = TestClient(app)
    bad_auth = client.post("/integrations/v1/zoho/leads", json={"record_id": "123"})
    assert bad_auth.status_code == 401

    monkeypatch.setattr(webhooks, "_verify_zoho_token", lambda _token: None)
    incomplete = client.post(
        "/integrations/v1/zoho/leads",
        json={"record_id": "123", "customer_name": "Asha", "source": "website", "message": ""},
    )
    assert incomplete.status_code == 422


class _FakeTable:
    def __init__(self, name):
        self.name = name
        self.event = None
        self.items = {}

    def get_item(self, Key, **_kwargs):
        if self.name == "test-suppressions":
            marker = Key["suppression_key"]
            if marker in {"migration", "history"}:
                return {"Item": {"index_key_scheme": "hmac-sha256-v1", "index_key_id": "key-v1"}}
        if self.name == "test-events":
            event_key = Key.get("event_key")
            if self.event and self.event.get("event_key") == event_key:
                return {"Item": self.event}
            return {"Item": self.items[event_key]} if event_key in self.items else {}
        return {}

    def update_item(self, *, Key, ExpressionAttributeValues, **_kwargs):
        if self.name != "test-events" or not self.event or self.event.get("event_key") != Key["event_key"]:
            raise AssertionError("Unexpected fake event marker update")
        if ":record_id" in ExpressionAttributeValues:
            self.event["source_record_id"] = ExpressionAttributeValues[":record_id"]
        if ":source_time" in ExpressionAttributeValues:
            self.event["source_modified_at"] = ExpressionAttributeValues[":source_time"]

    def put_item(self, *, Item, **_kwargs):
        if self.name != "test-events":
            raise AssertionError("Unexpected fake event item")
        event_key = Item["event_key"]
        if (self.event and self.event.get("event_key") == event_key) or event_key in self.items:
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException", "Message": "already exists"}}, "PutItem")
        self.items[event_key] = Item


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
    monkeypatch.setattr(integration_persistence, "settings", TestSettings())
    monkeypatch.setattr(integration_persistence, "suppression_keys", lambda *_args: [])


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


def test_permanent_external_record_marker_does_not_expire(monkeypatch):
    fake = _FakeDynamo()
    _patch_fake_dynamo(monkeypatch, fake)
    lead = Lead(customer_name="Asha Rao", source="website", raw_message="Need a quote", tenant_id="tenant-test")
    audit = AuditEvent(lead_id=lead.lead_id, tenant_id="tenant-test", tenant_lead_id=f"tenant-test#{lead.lead_id}", action="lead_received", actor="integration:zoho-crm")

    response = webhooks._create_or_return_duplicate(
        lead,
        audit,
        "tenant-test#external-record",
        "zoho-crm",
        "event-digest",
        "payload-digest",
        permanent_idempotency=True,
        source_modified_at="2026-10-10T12:00:00+00:00",
        source_record_id="5725767000000123456",
    )

    marker = fake.transact_items[2]["Put"]["Item"]
    assert response.status_code == 201
    assert marker["provider"]["S"] == "zoho-crm"
    assert marker["source_modified_at"]["S"] == "2026-10-10T12:00:00+00:00"
    assert marker["source_record_id"]["S"] == "5725767000000123456"
    assert "expires_at" not in marker
    binding = fake.transact_items[3]["Put"]["Item"]
    assert binding["event_key"]["S"] == f"tenant-test#zoho-binding#{lead.lead_id}"
    assert binding["source_record_id"]["S"] == "5725767000000123456"


def test_zoho_source_binding_uses_tenant_scoped_strong_key(monkeypatch):
    expected_key = "tenant-test#zoho-binding#local-lead"

    class BindingTable:
        def get_item(self, *, Key, ConsistentRead):
            assert Key == {"event_key": expected_key}
            assert ConsistentRead is True
            return {"Item": {
                "event_key": expected_key,
                "tenant_id": "tenant-test",
                "provider": "zoho-crm",
                "lead_id": "local-lead",
                "source_record_id": "5725767000000123456",
            }}

    class Resource:
        def Table(self, _name):
            return BindingTable()

    class TestSettings:
        effective_tenant_id = "tenant-test"
        processed_events_table = "test-events"

    monkeypatch.setattr(zoho, "settings", TestSettings())
    monkeypatch.setattr(zoho, "get_boto3_dynamodb_resource", Resource)
    assert zoho.source_record_id_for_lead("local-lead") == "5725767000000123456"


def test_zoho_source_binding_rejects_cross_tenant_or_malformed_records(monkeypatch):
    class BindingTable:
        def get_item(self, **_kwargs):
            return {"Item": {
                "tenant_id": "other-tenant",
                "provider": "zoho-crm",
                "lead_id": "local-lead",
                "source_record_id": "5725767000000123456",
            }}

    class Resource:
        def Table(self, _name):
            return BindingTable()

    class TestSettings:
        effective_tenant_id = "tenant-test"
        processed_events_table = "test-events"

    monkeypatch.setattr(zoho, "settings", TestSettings())
    monkeypatch.setattr(zoho, "get_boto3_dynamodb_resource", Resource)
    with pytest.raises(HTTPException) as exc:
        zoho.source_record_id_for_lead("local-lead")
    assert exc.value.status_code == 503


def test_zoho_replay_backfills_missing_source_version_only_for_identical_payload(monkeypatch):
    event = {
        "event_key": "tenant-test#external-record",
        "tenant_id": "tenant-test",
        "provider": "zoho-crm",
        "payload_digest": "same-payload",
        "lead_id": "existing-lead",
    }
    fake = _FakeDynamo(fail_transaction=True, event=event)
    _patch_fake_dynamo(monkeypatch, fake)
    lead = Lead(customer_name="Asha Rao", source="website", raw_message="Need a quote", tenant_id="tenant-test")
    event_marker = fake.tables["test-events"]
    # The event marker is known; this create replay may backfill its missing source version.
    digest = "same-payload"
    response = webhooks._create_or_return_duplicate(
        lead,
        AuditEvent(lead_id=lead.lead_id, tenant_id="tenant-test", tenant_lead_id=f"tenant-test#{lead.lead_id}", action="lead_received", actor="integration:zoho-crm"),
        "tenant-test#external-record",
        "zoho-crm",
        "event-digest",
        digest,
        permanent_idempotency=True,
        source_modified_at="2026-10-10T12:00:00+00:00",
        source_record_id="record-1",
    )

    assert response.status_code == 200
    assert json.loads(response.body)["duplicate"] is True
    assert event_marker.event["source_modified_at"] == "2026-10-10T12:00:00+00:00"
    assert event_marker.event["source_record_id"] == "record-1"
    assert event_marker.items["tenant-test#zoho-binding#existing-lead"]["source_record_id"] == "record-1"


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
