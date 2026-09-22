"""
LeadRescue AI — Config Repository
Provides persistence for Business Configuration (DynamoDB & Memory fallback).
"""

from typing import Dict, Optional
from decimal import Decimal
from botocore.exceptions import ClientError
from boto3.dynamodb.types import TypeSerializer
from app.config.settings import settings
from app.models.config import ConfigModel, ConfigUpdate
from app.models.audit import AuditEvent
from app.repositories.base import get_boto3_dynamodb_resource

DEFAULT_BUSINESS_CONFIG = {
    "config_key": "business_rules",
    "config_value": {
        "response_target_minutes": 20,
        "high_value_threshold": 50000,
        "business_name": "Your business",
        "supported_locations": [],
    },
}


class ConcurrentConfigUpdateError(Exception):
    """Raised when business rules changed after an administrator loaded them."""


def _serialize_item(item: dict) -> dict:
    serializer = TypeSerializer()

    def normalize(value):
        if isinstance(value, float):
            return Decimal(str(value))
        if isinstance(value, dict):
            return {key: normalize(child) for key, child in value.items()}
        if isinstance(value, list):
            return [normalize(child) for child in value]
        return value

    return {key: serializer.serialize(normalize(value)) for key, value in item.items()}


class ConfigRepository:
    def __init__(self, use_memory: bool = False):
        self.use_memory = use_memory
        self._memory_store: Dict[str, ConfigModel] = {}
        self._table = None

        if not use_memory:
            dynamodb = get_boto3_dynamodb_resource()
            if dynamodb and settings.config_table:
                try:
                    self._table = dynamodb.Table(settings.config_table)
                except Exception:
                    if not settings.demo_enabled:
                        raise
                    self.use_memory = True
            else:
                if not settings.demo_enabled:
                    raise RuntimeError("DynamoDB is required when DEMO_MODE is disabled")
                self.use_memory = True

        # Initialize default config in memory store
        default_item = ConfigModel(**DEFAULT_BUSINESS_CONFIG)
        self._memory_store[default_item.config_key] = default_item

    def get_config(self, key: str = "business_rules") -> ConfigModel:
        if self.use_memory or not self._table:
            return self._memory_store.get(key, ConfigModel(**DEFAULT_BUSINESS_CONFIG))
        try:
            storage_key = f"{settings.effective_tenant_id}#{key}"
            response = self._table.get_item(Key={"config_key": storage_key})
            item = response.get("Item")
            if item:
                if item.get("tenant_id") != settings.effective_tenant_id:
                    raise RuntimeError("Business configuration tenant ownership mismatch")
                item["config_key"] = key
                return ConfigModel(**item)
            return self._memory_store.get(key, ConfigModel(**DEFAULT_BUSINESS_CONFIG))
        except Exception:
            if not settings.demo_enabled:
                raise
            return self._memory_store.get(key, ConfigModel(**DEFAULT_BUSINESS_CONFIG))

    def update_config(self, key: str, config_update: ConfigUpdate) -> ConfigModel:
        current = self.get_config(key)
        current.config_value.update(config_update.config_value)

        if self.use_memory or not self._table:
            self._memory_store[key] = current
            return current
        try:
            item = current.model_dump()
            item["config_key"] = f"{settings.effective_tenant_id}#{key}"
            item["tenant_id"] = settings.effective_tenant_id
            self._table.put_item(Item=item)
            return current
        except Exception:
            if not settings.demo_enabled:
                raise
            self._memory_store[key] = current
            return current

    def update_config_with_audit(self, key: str, config_update: ConfigUpdate, audit: AuditEvent, audit_repo) -> ConfigModel:
        """Atomically update tenant rules and append the corresponding audit event."""
        storage_key = f"{settings.effective_tenant_id}#{key}"
        if self.use_memory or not self._table:
            if not audit_repo.use_memory:
                raise RuntimeError("Config and audit records must use the same persistent storage mode")
            current = self._memory_store.get(key, ConfigModel(**DEFAULT_BUSINESS_CONFIG))
            merged = {**current.config_value, **config_update.config_value}
            updated = ConfigModel(config_key=key, config_value=merged)
            self._memory_store[key] = updated
            audit_repo.store(audit)
            return updated
        if audit_repo.use_memory or not audit_repo._table:
            raise RuntimeError("Config and audit records must use the same persistent storage mode")

        stored = self._table.get_item(Key={"config_key": storage_key}, ConsistentRead=True).get("Item")
        if stored and stored.get("tenant_id") != settings.effective_tenant_id:
            raise RuntimeError("Business configuration tenant ownership mismatch")
        current_value = stored.get("config_value", DEFAULT_BUSINESS_CONFIG["config_value"]) if stored else DEFAULT_BUSINESS_CONFIG["config_value"]
        merged = {**current_value, **config_update.config_value}
        updated = ConfigModel(config_key=key, config_value=merged)
        item = updated.model_dump(mode="json")
        item["config_key"] = storage_key
        item["tenant_id"] = settings.effective_tenant_id

        put = {
            "TableName": settings.config_table,
            "Item": _serialize_item(item),
        }
        if stored:
            put["ExpressionAttributeNames"] = {"#tenant": "tenant_id", "#updated": "updated_at"}
            put["ExpressionAttributeValues"] = {":tenant": _serialize_item({"v": settings.effective_tenant_id})["v"]}
            if "updated_at" in stored:
                put["ConditionExpression"] = "#tenant = :tenant AND #updated = :expected"
                put["ExpressionAttributeValues"][":expected"] = _serialize_item({"v": stored["updated_at"]})["v"]
            else:
                put["ConditionExpression"] = "#tenant = :tenant AND attribute_not_exists(#updated)"
        else:
            put["ConditionExpression"] = "attribute_not_exists(config_key)"

        try:
            self._table.meta.client.transact_write_items(
                TransactItems=[
                    {"Put": put},
                    {
                        "Put": {
                            "TableName": settings.audit_table,
                            "Item": _serialize_item(audit.model_dump(mode="json")),
                            "ConditionExpression": "attribute_not_exists(audit_id)",
                        }
                    },
                ]
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "TransactionCanceledException":
                raise ConcurrentConfigUpdateError("Business config changed after it was loaded") from exc
            raise
        return updated
