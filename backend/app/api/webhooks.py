"""Signed inbound lead webhooks with replay protection and atomic persistence."""

import hashlib
import hmac
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from boto3.dynamodb.types import TypeSerializer
from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from app.config.settings import settings
from app.models.audit import AuditEvent
from app.models.enums import LifecycleStatusEnum, SourceEnum
from app.models.lead import Lead
from app.repositories.base import get_boto3_dynamodb_resource
from app.repositories.customer_index import customer_index_keys
from app.repositories.customer_suppressions import migration_marker_key, suppression_items, suppression_keys
from app.policy.guardrails import check_opt_out

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations/v1", tags=["Integrations"])
_serializer = TypeSerializer()
_secret_value: Optional[str] = None
_secret_expires_at = 0.0
_MAX_CLOCK_SKEW_SECONDS = 300
_MAX_BODY_BYTES = 256_000
_IDEMPOTENCY_TTL_SECONDS = 60 * 60 * 24 * 30


class InboundLead(BaseModel):
    customer_name: str = Field(min_length=1, max_length=200)
    customer_email: Optional[EmailStr] = None
    customer_phone: Optional[str] = Field(default=None, max_length=64)
    source: SourceEnum
    message: str = Field(min_length=1, max_length=20000)


def _get_webhook_secret() -> str:
    global _secret_value, _secret_expires_at
    if not settings.webhook_secret_arn:
        raise HTTPException(status_code=503, detail="Inbound webhook integration is not configured")
    if _secret_value and time.monotonic() < _secret_expires_at:
        return _secret_value
    try:
        client = boto3.client("secretsmanager", region_name=settings.aws_region or None)
        response = client.get_secret_value(SecretId=settings.webhook_secret_arn)
        value = response.get("SecretString")
        if not value:
            raise ValueError("Configured webhook secret has no SecretString")
        try:
            decoded = json.loads(value)
            value = decoded.get("secret", value) if isinstance(decoded, dict) else value
        except json.JSONDecodeError:
            pass
        if not isinstance(value, str) or not value:
            raise ValueError("Configured webhook secret is empty")
        _secret_value = value
        _secret_expires_at = time.monotonic() + 60
        return value
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unable to read inbound webhook secret")
        raise HTTPException(status_code=503, detail="Inbound webhook integration is unavailable") from exc


def _verify_signature(body: bytes, timestamp: str, provider: str, event_id: str, signature: str) -> None:
    try:
        request_time = int(timestamp)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid webhook timestamp") from exc
    if abs(int(time.time()) - request_time) > _MAX_CLOCK_SKEW_SECONDS:
        raise HTTPException(status_code=401, detail="Webhook timestamp is outside the allowed window")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", provider):
        raise HTTPException(status_code=400, detail="Invalid webhook provider identifier")
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,256}", event_id):
        raise HTTPException(status_code=400, detail="Invalid idempotency key")

    canonical = timestamp.encode() + b"." + provider.encode() + b"." + event_id.encode() + b"." + body
    expected = "sha256=" + hmac.new(_get_webhook_secret().encode(), canonical, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.strip()):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


def _serialize(item: dict) -> dict:
    return {key: _serializer.serialize(value) for key, value in item.items()}


def _suppression_transaction_items(lead: Lead) -> list[dict]:
    keys = suppression_keys(settings.effective_tenant_id, lead.customer_email, lead.customer_phone)
    if lead.lifecycle_status == LifecycleStatusEnum.OPTED_OUT:
        return [
            {"Put": {"TableName": settings.customer_suppressions_table, "Item": _serialize(item)}}
            for item in suppression_items(settings.effective_tenant_id, lead.lead_id, lead.customer_email, lead.customer_phone)
        ]
    return [
        {
            "ConditionCheck": {
                "TableName": settings.customer_suppressions_table,
                "Key": _serialize({"suppression_key": key}),
                "ConditionExpression": "attribute_not_exists(suppression_key)",
            }
        }
        for key in keys if key
    ]


async def _read_bounded_body(request: Request) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Content-Length") from exc
        if declared_length < 0:
            raise HTTPException(status_code=400, detail="Invalid Content-Length")
        if declared_length > _MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Webhook body exceeds 256 KB")

    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > _MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Webhook body exceeds 256 KB")
        chunks.append(chunk)
    return b"".join(chunks)


def _create_or_return_duplicate(
    lead: Lead,
    audit: AuditEvent,
    event_key: str,
    provider: str,
    idempotency_digest: str,
    payload_digest: str,
) -> JSONResponse:
    dynamodb = get_boto3_dynamodb_resource()
    if not dynamodb:
        raise HTTPException(status_code=503, detail="Lead storage is unavailable")
    events_table = dynamodb.Table(settings.processed_events_table)
    suppressions_table = dynamodb.Table(settings.customer_suppressions_table)
    if not suppressions_table.get_item(
        Key={"suppression_key": migration_marker_key(settings.effective_tenant_id)},
        ConsistentRead=True,
    ).get("Item"):
        raise HTTPException(status_code=503, detail="Customer opt-out data is being migrated")
    if lead.lifecycle_status != LifecycleStatusEnum.OPTED_OUT:
        for key in suppression_keys(settings.effective_tenant_id, lead.customer_email, lead.customer_phone):
            if key and suppressions_table.get_item(Key={"suppression_key": key}, ConsistentRead=True).get("Item"):
                lead.lifecycle_status = LifecycleStatusEnum.OPTED_OUT
                audit.details["lifecycle_status"] = lead.lifecycle_status.value
                break
    marker = {
        "event_key": event_key,
        "tenant_id": settings.effective_tenant_id,
        "provider": provider,
        "event_digest": idempotency_digest,
        "payload_digest": payload_digest,
        "lead_id": lead.lead_id,
        "status": "COMPLETED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": int(time.time()) + _IDEMPOTENCY_TTL_SECONDS,
    }
    client = dynamodb.meta.client
    try:
        client.transact_write_items(
            TransactItems=[
                {
                    "Put": {
                        "TableName": settings.leads_table,
                        "Item": _serialize({
                            **lead.model_dump(),
                            **customer_index_keys(lead.tenant_id, lead.customer_email, lead.customer_phone),
                        }),
                        "ConditionExpression": "attribute_not_exists(lead_id)",
                    }
                },
                {
                    "Put": {
                        "TableName": settings.audit_table,
                        "Item": _serialize(audit.model_dump()),
                        "ConditionExpression": "attribute_not_exists(audit_id)",
                    }
                },
                {
                    "Put": {
                        "TableName": settings.processed_events_table,
                        "Item": _serialize(marker),
                        "ConditionExpression": "attribute_not_exists(event_key)",
                    }
                },
                *_suppression_transaction_items(lead),
            ]
        )
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={"accepted": True, "duplicate": False, "lead_id": lead.lead_id},
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code == "TransactionCanceledException":
            try:
                existing = events_table.get_item(Key={"event_key": event_key}, ConsistentRead=True).get("Item")
            except (ClientError, BotoCoreError) as read_error:
                raise HTTPException(status_code=503, detail="Could not confirm webhook idempotency") from read_error
            if existing and existing.get("tenant_id") == settings.effective_tenant_id:
                stored_digest = existing.get("payload_digest")
                # Older markers predate payload digests. Preserve their dedupe behavior
                # until the 30-day marker TTL removes them; new markers are strict.
                if stored_digest and not hmac.compare_digest(stored_digest, payload_digest):
                    raise HTTPException(status_code=409, detail="Idempotency key was already used for a different payload")
                if existing.get("provider") != provider or not existing.get("lead_id"):
                    raise HTTPException(status_code=503, detail="Stored webhook idempotency state is invalid")
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={"accepted": True, "duplicate": True, "lead_id": existing["lead_id"]},
                )
        logger.exception("Atomic webhook persistence failed")
        raise HTTPException(status_code=503, detail="Could not persist inbound lead") from exc
    except BotoCoreError as exc:
        logger.exception("Atomic webhook persistence failed")
        raise HTTPException(status_code=503, detail="Could not persist inbound lead") from exc


@router.post("/leads", summary="Receive a signed lead from a CRM or form system")
async def ingest_lead(
    request: Request,
    webhook_timestamp: str = Header(alias="X-Webhook-Timestamp"),
    webhook_signature: str = Header(alias="X-Webhook-Signature"),
    idempotency_key: str = Header(alias="Idempotency-Key"),
    provider: str = Header(default="generic", alias="X-Webhook-Provider"),
):
    """Validate a signed event, then atomically persist lead, audit, and dedupe marker."""
    body = await _read_bounded_body(request)
    await run_in_threadpool(_verify_signature, body, webhook_timestamp, provider, idempotency_key, webhook_signature)
    try:
        payload = InboundLead.model_validate_json(body)
    except ValidationError as exc:
        errors = [{"loc": item["loc"], "msg": item["msg"], "type": item["type"]} for item in exc.errors()]
        raise HTTPException(status_code=422, detail=errors) from exc

    idempotency_digest = hashlib.sha256(f"{provider}:{idempotency_key}".encode()).hexdigest()
    payload_digest = hashlib.sha256(body).hexdigest()
    event_key = f"{settings.effective_tenant_id}#{idempotency_digest}"
    lead = Lead(
        customer_name=payload.customer_name,
        customer_email=payload.customer_email,
        customer_phone=payload.customer_phone,
        source=payload.source,
        raw_message=payload.message,
    )
    opted_out, _ = check_opt_out(payload.message)
    if opted_out:
        lead.lifecycle_status = LifecycleStatusEnum.OPTED_OUT

    audit = AuditEvent(
        lead_id=lead.lead_id,
        tenant_id=settings.effective_tenant_id,
        tenant_lead_id=f"{settings.effective_tenant_id}#{lead.lead_id}",
        action="lead_received",
        actor=f"integration:{provider}",
        details={"source": payload.source.value, "event_digest": idempotency_digest, "lifecycle_status": lead.lifecycle_status.value},
    )
    return await run_in_threadpool(
        _create_or_return_duplicate,
        lead,
        audit,
        event_key,
        provider,
        idempotency_digest,
        payload_digest,
    )
