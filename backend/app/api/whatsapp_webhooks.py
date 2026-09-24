"""Authenticated Meta WhatsApp webhook verification and delivery-status ingestion."""

import json
import hmac
import re
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response

from app.api.deps import get_audit_repo, get_leads_repo, get_whatsapp_messages_repo
from app.integrations.whatsapp import WhatsAppConfigurationError, load_config, verify_webhook_signature
from app.repositories.audit import AuditRepository
from app.repositories.whatsapp_messages import WhatsAppMessagesRepository
from app.repositories.leads import LeadsRepository
from app.policy.guardrails import check_opt_out

router = APIRouter(prefix="/integrations/v1/whatsapp", tags=["WhatsApp webhooks"])
_SUPPORTED_STATUS = {"sent", "delivered", "read", "failed"}
_EXACT_OPT_OUT_WORDS = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit"}


def _inbound_message_text(message: dict) -> Optional[str]:
    message_type = message.get("type")
    if message_type == "text" and isinstance(message.get("text"), dict):
        return message["text"].get("body")
    if message_type == "button" and isinstance(message.get("button"), dict):
        return " ".join(str(message["button"].get(key, "")) for key in ("text", "payload"))
    if message_type == "interactive" and isinstance(message.get("interactive"), dict):
        choice = message["interactive"].get("button_reply") or message["interactive"].get("list_reply") or {}
        if isinstance(choice, dict):
            return " ".join(str(choice.get(key, "")) for key in ("title", "id"))
    return None


@router.get("/webhook", include_in_schema=False)
def verify_meta_webhook(
    mode: Optional[str] = Query(None, alias="hub.mode"),
    verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    if mode != "subscribe" or not challenge:
        raise HTTPException(status_code=400, detail="Invalid webhook verification request")
    try:
        config = load_config()
    except WhatsAppConfigurationError as exc:
        raise HTTPException(status_code=503, detail="WhatsApp webhook is not configured") from exc
    if not verify_token or not hmac.compare_digest(verify_token, config.verify_token):
        raise HTTPException(status_code=403, detail="Webhook verification failed")
    return Response(content=challenge, media_type="text/plain")


@router.post("/webhook")
async def receive_meta_webhook(
    request: Request,
    signature: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    messages_repo: WhatsAppMessagesRepository = Depends(get_whatsapp_messages_repo),
    leads_repo: LeadsRepository = Depends(get_leads_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
):
    raw_body = await request.body()
    if len(raw_body) > 512 * 1024:
        raise HTTPException(status_code=413, detail="Webhook body is too large")
    try:
        config = load_config()
    except WhatsAppConfigurationError as exc:
        raise HTTPException(status_code=503, detail="WhatsApp webhook is not configured") from exc
    if not signature or not verify_webhook_signature(config.app_secret, raw_body, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    try:
        payload = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Malformed webhook JSON") from exc
    if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
        raise HTTPException(status_code=400, detail="Unexpected webhook object")
    entries = payload.get("entry")
    if not isinstance(entries, list):
        raise HTTPException(status_code=400, detail="Malformed webhook entries")

    processed = 0
    suppressed = 0
    event_count = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes", [])
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict) or not isinstance(change.get("value"), dict):
                continue
            value = change["value"]
            metadata = value.get("metadata") or {}
            if not isinstance(metadata, dict):
                continue
            if metadata.get("phone_number_id") != config.phone_number_id:
                continue
            statuses = value.get("statuses", [])
            if not isinstance(statuses, list):
                statuses = []
            for event in statuses:
                event_count += 1
                if event_count > 200:
                    raise HTTPException(status_code=413, detail="Webhook has too many status events")
                if not isinstance(event, dict):
                    continue
                provider_status = event.get("status")
                provider_message_id = event.get("id")
                try:
                    event_timestamp = int(event.get("timestamp"))
                except (TypeError, ValueError):
                    continue
                if (
                    provider_status not in _SUPPORTED_STATUS
                    or not isinstance(provider_message_id, str)
                    or not provider_message_id
                    or len(provider_message_id) > 256
                    or event_timestamp <= 0
                ):
                    continue
                correlation_id = event.get("biz_opaque_callback_data")
                message = None
                if isinstance(correlation_id, str) and re.fullmatch(r"[a-f0-9]{64}", correlation_id):
                    message = messages_repo.get(correlation_id)
                if not message:
                    message = messages_repo.find_by_provider_id(provider_message_id)
                if not message:
                    continue
                error_list = event.get("errors", [])
                first_error = error_list[0] if isinstance(error_list, list) and error_list and isinstance(error_list[0], dict) else {}
                provider_error_code = str(first_error.get("code"))[:32] if first_error.get("code") is not None else None
                messages_repo.apply_provider_status(
                    message.message_id,
                    provider_status,
                    provider_message_id,
                    event_timestamp,
                    audit_repo,
                    error_code=provider_error_code,
                )
                processed += 1
            inbound_messages = value.get("messages", [])
            if not isinstance(inbound_messages, list):
                inbound_messages = []
            for inbound in inbound_messages:
                event_count += 1
                if event_count > 200:
                    raise HTTPException(status_code=413, detail="Webhook has too many message events")
                if not isinstance(inbound, dict):
                    continue
                sender = inbound.get("from")
                event_id = inbound.get("id")
                try:
                    inbound_timestamp = int(inbound.get("timestamp"))
                except (TypeError, ValueError):
                    continue
                body = _inbound_message_text(inbound)
                if (
                    not isinstance(sender, str) or not re.fullmatch(r"[1-9]\d{7,14}", sender)
                    or not isinstance(event_id, str) or not event_id or len(event_id) > 256
                    or not isinstance(body, str) or len(body) > 4096
                    or inbound_timestamp <= 0 or inbound_timestamp > 4102444800
                ):
                    continue
                opted_out, _reason = check_opt_out(body)
                opted_out = opted_out or re.sub(r"[^a-z0-9]", "", body.lower()) in _EXACT_OPT_OUT_WORDS
                if opted_out:
                    leads_repo.record_whatsapp_phone_opt_out(f"+{sender}", event_id, inbound_timestamp, audit_repo)
                    suppressed += 1
    return {"received": event_count, "correlated": processed, "opt_outs_recorded": suppressed}
