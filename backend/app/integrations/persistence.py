"""Shared DynamoDB helpers for authenticated inbound integrations."""

import logging
from typing import Optional

from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException

from app.config.settings import settings
from app.models.enums import LifecycleStatusEnum
from app.models.lead import Lead
from app.repositories.customer_suppressions import suppression_items, suppression_keys

logger = logging.getLogger(__name__)
_serializer = TypeSerializer()


def serialize_item(item: dict) -> dict:
    """Convert a Python item to DynamoDB's low-level attribute-value format."""
    return {key: _serializer.serialize(value) for key, value in item.items()}


def consistent_item(table, key: dict, failure_detail: str) -> Optional[dict]:
    """Read one item consistently and fail closed when storage is unavailable."""
    try:
        return table.get_item(Key=key, ConsistentRead=True).get("Item")
    except (ClientError, BotoCoreError) as exc:
        logger.exception("Integration state read failed")
        raise HTTPException(status_code=503, detail=failure_detail) from exc


def suppression_transaction_items(lead: Lead) -> list[dict]:
    """Atomically record opt-outs or reject a new lead bound to a suppressed contact."""
    keys = suppression_keys(settings.effective_tenant_id, lead.customer_email, lead.customer_phone)
    if lead.lifecycle_status == LifecycleStatusEnum.OPTED_OUT:
        return [
            {"Put": {"TableName": settings.customer_suppressions_table, "Item": serialize_item(item)}}
            for item in suppression_items(settings.effective_tenant_id, lead.lead_id, lead.customer_email, lead.customer_phone)
        ]
    return [
        {
            "ConditionCheck": {
                "TableName": settings.customer_suppressions_table,
                "Key": serialize_item({"suppression_key": key}),
                "ConditionExpression": "attribute_not_exists(suppression_key)",
            }
        }
        for key in keys if key
    ]
