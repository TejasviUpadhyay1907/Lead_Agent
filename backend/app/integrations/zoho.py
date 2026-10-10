"""Zoho CRM webhook contracts and source-of-truth reconciliation."""

import hashlib
import hmac
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.config.settings import settings
from app.models.audit import AuditEvent
from app.models.enums import LifecycleStatusEnum, ResponseStatusEnum, RiskStatusEnum, SourceEnum
from app.models.lead import Lead
from app.models.privacy_request import PrivacyRequest
from app.policy.guardrails import check_opt_out, detect_privacy_request
from app.repositories.base import get_boto3_dynamodb_resource
from app.repositories.customer_index import CustomerIndexKeyUnavailableError, customer_index_keys, require_customer_index_key
from app.repositories.customer_suppressions import history_index_marker_key, migration_marker_key, suppression_keys
from app.integrations.persistence import consistent_item, serialize_item, suppression_transaction_items

logger = logging.getLogger(__name__)


class ZohoLeadWebhook(BaseModel):
    """Strict mapped snapshot accepted for Zoho lead creation."""

    record_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    customer_name: str = Field(min_length=1, max_length=200)
    customer_email: Optional[EmailStr] = None
    customer_phone: Optional[str] = Field(default=None, max_length=64)
    source: SourceEnum
    message: str = Field(min_length=1, max_length=20000)
    modified_at: Optional[datetime] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("customer_name", "message", mode="before")
    @classmethod
    def trim_required_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("customer_email", "customer_phone", mode="before")
    @classmethod
    def normalize_empty_contact_fields(cls, value):
        return None if value == "" else value

    @field_validator("modified_at", mode="before")
    @classmethod
    def require_zoned_source_time(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("modified_at must include a timezone offset")
        normalized = value.astimezone(timezone.utc)
        if normalized > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("modified_at cannot be in the future")
        return normalized


class ZohoLeadUpdateWebhook(ZohoLeadWebhook):
    """Complete Zoho snapshot with a source version for monotonic reconciliation."""

    modified_at: datetime = Field(...)

    @model_validator(mode="after")
    def require_complete_snapshot(self):
        if not {"customer_email", "customer_phone"}.issubset(self.model_fields_set):
            raise ValueError("customer_email and customer_phone must be present; use null to clear them")
        return self


def apply_lead_snapshot(payload: ZohoLeadUpdateWebhook, payload_digest: str) -> JSONResponse:
    """Apply a versioned CRM snapshot without overwriting LeadRescue-owned decisions."""
    dynamodb = get_boto3_dynamodb_resource()
    if not dynamodb:
        raise HTTPException(status_code=503, detail="Lead storage is unavailable")

    provider = "zoho-crm"
    event_digest = hashlib.sha256(f"{provider}:{payload.record_id}".encode()).hexdigest()
    event_key = f"{settings.effective_tenant_id}#{event_digest}"
    events_table = dynamodb.Table(settings.processed_events_table)
    existing = consistent_item(events_table, {"event_key": event_key}, "Could not read Zoho source binding")
    if not existing:
        raise HTTPException(status_code=404, detail="Zoho record has not been imported")
    if (
        existing.get("tenant_id") != settings.effective_tenant_id
        or existing.get("provider") != provider
        or not existing.get("lead_id")
        or existing.get("source_record_id") not in {None, payload.record_id}
    ):
        raise HTTPException(status_code=503, detail="Zoho source-record binding is invalid")

    previous_source_time = existing.get("source_modified_at")
    if not previous_source_time:
        raise HTTPException(
            status_code=409,
            detail="Zoho source version is missing; replay an identical create snapshot with Modified_Time before enabling updates",
        )
    try:
        previous_time = datetime.fromisoformat(previous_source_time.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Stored Zoho source version is invalid") from exc
    if previous_time.tzinfo is None or previous_time.utcoffset() is None:
        raise HTTPException(status_code=503, detail="Stored Zoho source version has no timezone")

    previous_time = previous_time.astimezone(timezone.utc)
    if payload.modified_at < previous_time:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"accepted": False, "stale": True, "lead_id": existing["lead_id"]},
        )
    if payload.modified_at == previous_time:
        if hmac.compare_digest(existing.get("payload_digest", ""), payload_digest):
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"accepted": True, "duplicate": True, "lead_id": existing["lead_id"]},
            )
        raise HTTPException(status_code=409, detail="Zoho sent different lead data for the same source version")

    leads_table = dynamodb.Table(settings.leads_table)
    stored = consistent_item(leads_table, {"lead_id": existing["lead_id"]}, "Could not read the linked lead")
    if not stored or stored.get("tenant_id") != settings.effective_tenant_id:
        raise HTTPException(status_code=503, detail="Zoho source record points to a missing local lead")
    lead = Lead(**stored)
    old_updated_at = lead.updated_at
    snapshot_values = {
        "customer_name": payload.customer_name,
        "customer_email": payload.customer_email,
        "customer_phone": payload.customer_phone,
        "source": payload.source,
        "raw_message": payload.message,
    }
    changed_fields = [field for field, value in snapshot_values.items() if getattr(lead, field) != value]

    if changed_fields:
        for field, value in snapshot_values.items():
            setattr(lead, field, value)
        lead.intent = None
        lead.urgency = None
        lead.product = None
        lead.quantity = None
        lead.location = None
        lead.customer_stage = None
        lead.key_entities = []
        lead.ai_summary = None
        lead.recommended_action = None
        lead.response_draft = None
        lead.score = None
        lead.score_breakdown = {}
        lead.priority = None
        lead.risk_status = RiskStatusEnum.NORMAL
        lead.at_risk_at = None
        lead.approved_draft_sha256 = None
        lead.approval_attested_at = None
        lead.approval_attested_by = None
        if lead.response_status not in {ResponseStatusEnum.SENT, ResponseStatusEnum.SIMULATED_SENT}:
            lead.response_status = None
        if "customer_phone" in changed_fields:
            lead.whatsapp_consent = None
        lead.last_analysis_job_id = None
        lead.updated_at = _next_updated_at(old_updated_at)

    privacy_request_type = detect_privacy_request(payload.message)
    new_privacy_request = None
    if privacy_request_type and privacy_request_type != detect_privacy_request(stored.get("raw_message", "")):
        new_privacy_request = PrivacyRequest(
            lead_id=lead.lead_id,
            request_type=privacy_request_type,
            source="integration:zoho-crm",
        )
        lead.privacy_hold = True
        if privacy_request_type == "erasure":
            lead.lifecycle_status = LifecycleStatusEnum.OPTED_OUT

    opted_out, _ = check_opt_out(payload.message)
    if opted_out:
        lead.lifecycle_status = LifecycleStatusEnum.OPTED_OUT

    suppressions_table = dynamodb.Table(settings.customer_suppressions_table)
    migration_marker = consistent_item(
        suppressions_table,
        {"suppression_key": migration_marker_key(settings.effective_tenant_id)},
        "Could not read customer opt-out migration state",
    )
    history_marker = consistent_item(
        suppressions_table,
        {"suppression_key": history_index_marker_key(settings.effective_tenant_id)},
        "Could not read customer identity-index state",
    )
    try:
        active_index_key_id = require_customer_index_key()
    except CustomerIndexKeyUnavailableError as exc:
        logger.exception("Customer identity-index key unavailable")
        raise HTTPException(status_code=503, detail="Customer identity-index key is unavailable") from exc
    if (
        not migration_marker
        or migration_marker.get("index_key_scheme") != "hmac-sha256-v1"
        or migration_marker.get("index_key_id") != active_index_key_id
        or not history_marker
        or history_marker.get("index_key_scheme") != "hmac-sha256-v1"
        or history_marker.get("index_key_id") != active_index_key_id
    ):
        raise HTTPException(status_code=503, detail="Customer opt-out data is being migrated")
    for key in suppression_keys(settings.effective_tenant_id, lead.customer_email, lead.customer_phone):
        if key and consistent_item(
            suppressions_table,
            {"suppression_key": key},
            "Could not verify contact suppression state",
        ):
            lead.lifecycle_status = LifecycleStatusEnum.OPTED_OUT
            break

    source_time = payload.modified_at.astimezone(timezone.utc).isoformat()
    audit = AuditEvent(
        lead_id=lead.lead_id,
        tenant_id=settings.effective_tenant_id,
        tenant_lead_id=f"{settings.effective_tenant_id}#{lead.lead_id}",
        action="zoho_lead_snapshot_updated",
        actor="integration:zoho-crm",
        details={
            "source_record_digest": event_digest,
            "source_modified_at": source_time,
            "changed_fields": changed_fields,
            "privacy_request_type": privacy_request_type if new_privacy_request else None,
            "lifecycle_status": lead.lifecycle_status.value,
        },
    )
    transaction = [
        {
            "Put": {
                "TableName": settings.leads_table,
                "Item": serialize_item({
                    **lead.model_dump(),
                    **customer_index_keys(lead.tenant_id, lead.customer_email, lead.customer_phone),
                }),
                "ConditionExpression": "tenant_id = :tenant AND updated_at = :expected_updated_at",
                "ExpressionAttributeValues": serialize_item({
                    ":tenant": settings.effective_tenant_id,
                    ":expected_updated_at": old_updated_at,
                }),
            }
        },
        {
            "Put": {
                "TableName": settings.audit_table,
                "Item": serialize_item(audit.model_dump()),
                "ConditionExpression": "attribute_not_exists(audit_id)",
            }
        },
        {
            "Update": {
                "TableName": settings.processed_events_table,
                "Key": serialize_item({"event_key": event_key}),
                "UpdateExpression": "SET source_modified_at = :source_time, payload_digest = :payload_digest",
                "ConditionExpression": "attribute_exists(event_key) AND tenant_id = :tenant AND provider = :provider AND source_modified_at = :previous",
                "ExpressionAttributeValues": serialize_item({
                    ":tenant": settings.effective_tenant_id,
                    ":provider": provider,
                    ":previous": previous_source_time,
                    ":source_time": source_time,
                    ":payload_digest": payload_digest,
                }),
            }
        },
        *suppression_transaction_items(lead),
    ]
    if new_privacy_request:
        transaction.append({
            "Put": {
                "TableName": settings.privacy_requests_table,
                "Item": serialize_item(new_privacy_request.model_dump(mode="json")),
                "ConditionExpression": "attribute_not_exists(request_id)",
            }
        })

    try:
        dynamodb.meta.client.transact_write_items(TransactItems=transaction)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "TransactionCanceledException":
            raise HTTPException(status_code=409, detail="Zoho record changed concurrently; retry the latest complete snapshot") from exc
        logger.exception("Atomic Zoho snapshot update failed")
        raise HTTPException(status_code=503, detail="Could not persist Zoho lead update") from exc
    except BotoCoreError as exc:
        logger.exception("Atomic Zoho snapshot update failed")
        raise HTTPException(status_code=503, detail="Could not persist Zoho lead update") from exc

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"accepted": True, "updated": True, "lead_id": lead.lead_id, "changed_fields": changed_fields},
    )


def source_record_id_for_lead(lead_id: str) -> Optional[str]:
    """Return the durable Zoho record binding for a tenant-owned local lead."""
    dynamodb = get_boto3_dynamodb_resource()
    if not dynamodb:
        raise HTTPException(status_code=503, detail="Lead storage is unavailable")
    binding_key = f"{settings.effective_tenant_id}#zoho-binding#{lead_id}"
    item = consistent_item(
        dynamodb.Table(settings.processed_events_table),
        {"event_key": binding_key},
        "Could not read Zoho source-record binding",
    )
    if not item:
        return None
    record_id = item.get("source_record_id")
    if (
        item.get("tenant_id") != settings.effective_tenant_id
        or item.get("provider") != "zoho-crm"
        or item.get("lead_id") != lead_id
        or not isinstance(record_id, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", record_id)
    ):
        raise HTTPException(status_code=503, detail="Zoho source-record binding is invalid")
    return record_id


def _next_updated_at(previous: str) -> str:
    current = datetime.now(timezone.utc)
    try:
        previous_time = datetime.fromisoformat(previous.replace("Z", "+00:00"))
        if previous_time.tzinfo is not None and current <= previous_time:
            current = previous_time.astimezone(timezone.utc) + timedelta(microseconds=1)
    except (AttributeError, ValueError):
        pass
    return current.isoformat()
