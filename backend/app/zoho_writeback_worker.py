"""DynamoDB Streams consumer for transactional Zoho outcome writeback events."""

import logging
import json
import uuid
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.types import TypeDeserializer

from app.config.settings import settings
from app.integrations.zoho_writeback import ZohoWritebackError, update_lead_outcome
from app.models.audit import AuditEvent

logger = logging.getLogger("leadrescue.zoho_writeback")
_deserializer = TypeDeserializer()


def _deserialize(image: dict) -> dict:
    return {key: _deserializer.deserialize(value) for key, value in image.items()}


def _set_lead_status(item: dict, status: str, error_code: str | None = None) -> None:
    dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region or None)
    table = dynamodb.Table(settings.leads_table)
    names = {"#status": "crm_sync_status", "#updated": "crm_sync_updated_at", "#error": "crm_sync_error_code"}
    values = {":tenant": settings.effective_tenant_id, ":event": item["event_id"], ":status": status, ":updated": datetime.now(timezone.utc).isoformat()}
    update = "SET #status = :status, #updated = :updated"
    if error_code:
        update += ", #error = :error"
        values[":error"] = error_code
    else:
        update += " REMOVE #error"
    try:
        table.update_item(
            Key={"lead_id": item["lead_id"]},
            UpdateExpression=update,
            ConditionExpression="tenant_id = :tenant AND crm_sync_event_id = :event",
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
            raise


def _writeback_state(item: dict) -> str:
    dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region or None)
    response = dynamodb.Table(settings.leads_table).get_item(
        Key={"lead_id": item["lead_id"]},
        ConsistentRead=True,
        ProjectionExpression="tenant_id, crm_sync_event_id, privacy_hold, lifecycle_status",
    )
    lead = response.get("Item") or {}
    if lead.get("tenant_id") != settings.effective_tenant_id or lead.get("crm_sync_event_id") != item["event_id"]:
        return "superseded"
    if lead.get("privacy_hold") or lead.get("lifecycle_status") == "opted_out":
        return "blocked"
    return "current"


def _mark_outbox(item: dict, status: str, error_code: str | None = None) -> None:
    dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region or None)
    table = dynamodb.Table(settings.zoho_writeback_outbox_table)
    table.update_item(
        Key={"tenant_lead_key": item["tenant_lead_key"], "event_id": item["event_id"]},
        UpdateExpression="SET #status = :status, updated_at = :updated, error_code = :error",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":status": status,
            ":updated": datetime.now(timezone.utc).isoformat(),
            ":error": error_code or "",
        },
    )


def _record_audit(item: dict, status: str, error_code: str | None = None) -> None:
    dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region or None)
    audit_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"leadrescue:zoho-writeback:{item['event_id']}:{status}"))
    audit = AuditEvent(
        audit_id=audit_id,
        tenant_id=settings.effective_tenant_id,
        tenant_lead_id=f"{settings.effective_tenant_id}#{item['lead_id']}",
        lead_id=item["lead_id"],
        action=f"zoho_outcome_writeback_{status}",
        actor="system",
        details={"event_id": item["event_id"], **({"error_code": error_code} if error_code else {})},
    )
    try:
        dynamodb.Table(settings.audit_table).put_item(
            Item=audit.model_dump(mode="json"),
            ConditionExpression="attribute_not_exists(audit_id)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
            raise


def handler(event, _context):
    failures = []
    for record in event.get("Records", []):
        item = None
        sequence = record.get("dynamodb", {}).get("SequenceNumber")
        identifier = sequence or record.get("messageId")
        try:
            if record.get("eventSource") == "aws:sqs":
                envelope = json.loads(record.get("body", "{}"))
                failed_records = envelope.get("requestPayload", {}).get("Records", [])
                for failed in failed_records:
                    image = failed.get("dynamodb", {}).get("NewImage")
                    if image:
                        failed_item = _deserialize(image)
                        if failed_item.get("tenant_id") != settings.effective_tenant_id:
                            continue
                        _set_lead_status(failed_item, "failed", "retry_exhausted")
                        _mark_outbox(failed_item, "failed", "retry_exhausted")
                        _record_audit(failed_item, "failed", "retry_exhausted")
                continue
            if record.get("eventName") != "INSERT":
                continue
            raw = record.get("dynamodb", {}).get("NewImage")
            if not raw:
                continue
            item = _deserialize(raw)
            if item.get("tenant_id") != settings.effective_tenant_id:
                logger.error("Rejected Zoho outbox item from an unexpected tenant")
                continue
            state = _writeback_state(item)
            if state == "superseded":
                _mark_outbox(item, "superseded")
                _record_audit(item, "superseded")
                continue
            if state == "blocked":
                _set_lead_status(item, "failed", "privacy_or_opt_out_hold")
                _mark_outbox(item, "failed", "privacy_or_opt_out_hold")
                _record_audit(item, "failed", "privacy_or_opt_out_hold")
                continue
            update_lead_outcome(item["source_record_id"], item["fields"])
            _set_lead_status(item, "synced")
            _mark_outbox(item, "synced")
            _record_audit(item, "synced")
        except ZohoWritebackError as exc:
            if exc.retryable:
                failures.append({"itemIdentifier": identifier})
                continue
            try:
                status = "conflict" if exc.code == "crm_record_changed" else "failed"
                if item:
                    _set_lead_status(item, status, exc.code)
                    _mark_outbox(item, status, exc.code)
                    _record_audit(item, status, exc.code)
            except Exception as status_exc:
                logger.error("Could not record Zoho writeback failure (%s)", type(status_exc).__name__)
                failures.append({"itemIdentifier": identifier})
        except Exception as exc:
            logger.warning("Zoho writeback attempt failed (%s)", type(exc).__name__)
            failures.append({"itemIdentifier": identifier})
    return {"batchItemFailures": failures}
