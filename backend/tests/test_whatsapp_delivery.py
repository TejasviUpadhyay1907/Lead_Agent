import hashlib
import hmac
import json
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import leads as leads_api
from app.api.deps import get_audit_repo, get_leads_repo, get_whatsapp_messages_repo
from app.api.leads import WhatsAppSendRequest, send_whatsapp_message
from app.config.settings import Settings, settings
from app.integrations.whatsapp import WhatsAppConfig, WhatsAppSendResult
from app.main import app
from app.models.audit import AuditEventCreate
from app.models.enums import LifecycleStatusEnum, ResponseStatusEnum, WhatsAppConsentSourceEnum
from app.models.lead import Lead, WhatsAppConsent
from app.models.whatsapp_message import WhatsAppDeliveryStatus, WhatsAppMessage
from app.repositories.audit import AuditRepository
from app.repositories.leads import LeadsRepository
from app.repositories.whatsapp_messages import WhatsAppMessagesRepository
from app.repositories.customer_index import customer_index_keys


def _config():
    return WhatsAppConfig(
        access_token="test-token",
        phone_number_id="123456789012345",
        app_secret="test-app-secret",
        verify_token="test-verify-token",
        api_version="v23.0",
        template_name="leadrescue_reply",
        template_language="en",
        template_body="Hello {{1}}",
    )


def _verified_lead(lead_id="wa-delivery-test"):
    phone = "+14155552671"
    phone_key = customer_index_keys(settings.effective_tenant_id, None, phone)["tenant_phone_key"]
    draft = "Thanks for your interest. Our team will follow up shortly."
    draft_hash = hashlib.sha256(draft.encode()).hexdigest()
    return Lead(
        lead_id=lead_id,
        customer_name="Pilot Contact",
        customer_phone=phone,
        raw_message="Please send details.",
        lifecycle_status=LifecycleStatusEnum.NEW,
        response_status=ResponseStatusEnum.APPROVED,
        response_draft=draft,
        approved_draft_sha256=draft_hash,
        approval_attested_at=datetime.now(timezone.utc).isoformat(),
        approval_attested_by="pilot-operator",
        whatsapp_consent=WhatsAppConsent(
            consented_at=datetime.now(timezone.utc).isoformat(),
            recorded_at=datetime.now(timezone.utc).isoformat(),
            source=WhatsAppConsentSourceEnum.WEBSITE_FORM,
            evidence_ref=f"form-{lead_id}",
            text_version="wa-consent-v1",
            recipient_phone_key=phone_key,
            recorded_by="pilot-operator",
        ),
    )


@pytest.fixture
def sending_context(monkeypatch):
    # Exercise the production guard while keeping storage and provider calls local.
    monkeypatch.setattr("app.repositories.customer_index._get_index_hmac_key", lambda: b"x" * 32)
    leads = LeadsRepository(use_memory=True)
    audit = AuditRepository(use_memory=True)
    messages = WhatsAppMessagesRepository(use_memory=True)
    monkeypatch.setattr(Settings, "demo_enabled", property(lambda _self: False))
    monkeypatch.setattr(Settings, "effective_tenant_id", property(lambda _self: "demo"))
    monkeypatch.setattr(settings, "whatsapp_outbound_enabled", True)
    monkeypatch.setattr(settings, "whatsapp_secret_arn", "test-secret")
    monkeypatch.setattr(leads_api, "load_whatsapp_config", _config)
    lead = _verified_lead()
    leads._memory_store[lead.lead_id] = lead
    return leads, audit, messages, lead


def test_whatsapp_send_is_one_attempt_per_approval_and_binds_rendered_template(sending_context, monkeypatch):
    leads, audit, messages, lead = sending_context
    calls = []

    def fake_send(config, phone, draft, callback_id):
        calls.append((phone, draft, callback_id))
        return WhatsAppSendResult("accepted", provider_message_id="wamid.test-1")

    monkeypatch.setattr(leads_api, "send_approved_template", fake_send)
    operator = {"sub": "pilot-operator"}
    first = send_whatsapp_message(
        lead.lead_id, WhatsAppSendRequest(send_confirmed=True), operator, leads, audit, messages,
    )
    replay = send_whatsapp_message(
        lead.lead_id, WhatsAppSendRequest(send_confirmed=True), operator, leads, audit, messages,
    )

    assert first.status == WhatsAppDeliveryStatus.ACCEPTED
    assert replay.message_id == first.message_id
    assert len(calls) == 1
    assert first.rendered_message == "Hello Thanks for your interest. Our team will follow up shortly."
    assert first.rendered_message_sha256 == hashlib.sha256(first.rendered_message.encode()).hexdigest()
    assert len(audit.list_by_lead(lead.lead_id)) == 2


def test_whatsapp_send_fails_closed_for_phone_mismatch_and_does_not_call_provider(sending_context, monkeypatch):
    leads, audit, messages, lead = sending_context
    lead.customer_phone = "+14155552672"
    leads._memory_store[lead.lead_id] = lead
    called = False

    def fake_send(*_args):
        nonlocal called
        called = True
        return WhatsAppSendResult("accepted", provider_message_id="wamid.should-not-send")

    monkeypatch.setattr(leads_api, "send_approved_template", fake_send)
    with pytest.raises(HTTPException) as error:
        send_whatsapp_message(
            lead.lead_id, WhatsAppSendRequest(send_confirmed=True), {"sub": "pilot-operator"}, leads, audit, messages,
        )

    assert error.value.status_code == 409
    assert not called
    assert messages.list_for_lead(lead.lead_id) == []


def test_ambiguous_whatsapp_attempt_is_never_retried_for_the_same_approval(sending_context, monkeypatch):
    leads, audit, messages, lead = sending_context
    calls = []

    def fake_send(*_args):
        calls.append(True)
        return WhatsAppSendResult("unknown", error_code="transport_or_response_ambiguous")

    monkeypatch.setattr(leads_api, "send_approved_template", fake_send)
    args = (lead.lead_id, WhatsAppSendRequest(send_confirmed=True), {"sub": "pilot-operator"}, leads, audit, messages)
    first = send_whatsapp_message(*args)
    second = send_whatsapp_message(*args)

    assert first.status == WhatsAppDeliveryStatus.UNKNOWN
    assert second.message_id == first.message_id
    assert second.status == WhatsAppDeliveryStatus.UNKNOWN
    assert len(calls) == 1


def test_signed_meta_status_webhook_updates_once_and_stop_suppresses_phone(monkeypatch):
    config = _config()
    monkeypatch.setattr("app.api.whatsapp_webhooks.load_config", lambda: config)
    messages = get_whatsapp_messages_repo()
    leads = get_leads_repo()
    audit = get_audit_repo()
    message_id = hashlib.sha256(b"webhook-test").hexdigest()
    lead_id = "wa-webhook-test"
    message = WhatsAppMessage(
        message_id=message_id,
        lead_id=lead_id,
        status=WhatsAppDeliveryStatus.SUBMITTING,
        initiated_by="pilot-operator",
        approved_draft_sha256="a" * 64,
        approval_attested_at=datetime.now(timezone.utc).isoformat(),
        template_body_sha256="b" * 64,
        rendered_message_sha256="c" * 64,
        rendered_message="Approved text.",
        consent_evidence_ref="form-webhook-test",
        recipient_phone_key="demo#phone-key",
        template_name=config.template_name,
        template_language=config.template_language,
        provider_api_version=config.api_version,
    )
    messages.create_attempt(message, audit.build(AuditEventCreate(
        lead_id=lead_id, action="whatsapp_send_attempt_started", actor="user:pilot-operator",
    )), audit)

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {
            "metadata": {"phone_number_id": config.phone_number_id},
            "statuses": [{
                "id": "wamid.webhook-test", "status": "delivered", "timestamp": "1780000000",
                "biz_opaque_callback_data": message_id,
            }],
            "messages": [{"id": "wamid.stop-test", "from": "14155552673", "timestamp": "1780000001",
                          "type": "text", "text": {"body": "STOP"}}],
        }}]}],
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    signature = "sha256=" + hmac.new(config.app_secret.encode(), raw, hashlib.sha256).hexdigest()
    client = TestClient(app)
    response = client.post(
        "/integrations/v1/whatsapp/webhook",
        content=raw,
        headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json() == {"received": 2, "correlated": 1, "opt_outs_recorded": 1}
    assert messages.get(message_id).status == WhatsAppDeliveryStatus.DELIVERED
    audit_count = len(audit.list_by_lead(lead_id))
    replay = client.post(
        "/integrations/v1/whatsapp/webhook",
        content=raw,
        headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"},
    )
    assert replay.status_code == 200
    assert len(audit.list_by_lead(lead_id)) == audit_count
    suppressed = _verified_lead("wa-stop-check")
    suppressed.customer_phone = "+14155552673"
    assert leads.customer_opted_out(suppressed)


def test_meta_webhook_rejects_invalid_signature(monkeypatch):
    monkeypatch.setattr("app.api.whatsapp_webhooks.load_config", _config)
    response = TestClient(app).post(
        "/integrations/v1/whatsapp/webhook",
        json={"object": "whatsapp_business_account", "entry": []},
        headers={"X-Hub-Signature-256": "sha256=" + "0" * 64},
    )
    assert response.status_code == 401
