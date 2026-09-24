"""Atomic persistence for WhatsApp attempts, provider statuses, and audit events."""

from typing import Optional

from boto3.dynamodb.types import TypeSerializer
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from app.config.settings import settings
from app.models.audit import AuditEvent, AuditEventCreate
from app.models.whatsapp_message import WhatsAppDeliveryStatus, WhatsAppMessage, now_iso
from app.repositories.base import get_boto3_dynamodb_resource

_serializer = TypeSerializer()
_STATUS_RANK = {"sent": 1, "delivered": 2, "read": 3, "failed": 4}


def _av(value):
    # Omit top-level optional DynamoDB fields so sparse GSI keys stay absent.
    return {key: _serializer.serialize(item) for key, item in value.items() if item is not None}


class WhatsAppMessagesRepository:
    def __init__(self, use_memory: bool = False):
        self._memory: dict[str, WhatsAppMessage] = {}
        self.use_memory = use_memory or settings.demo_enabled
        resource = get_boto3_dynamodb_resource() if not self.use_memory else None
        self._table = (
            resource.Table(settings.whatsapp_messages_table)
            if resource and settings.whatsapp_messages_table and not self.use_memory
            else None
        )
        if self._table is None and not self.use_memory:
            raise RuntimeError("Durable WhatsApp message storage is required")

    def get(self, message_id: str) -> Optional[WhatsAppMessage]:
        if self._table is None:
            item = self._memory.get(message_id)
            return item.model_copy(deep=True) if item and item.tenant_id == settings.effective_tenant_id else None
        item = self._table.get_item(Key={"message_id": message_id}, ConsistentRead=True).get("Item")
        return WhatsAppMessage(**item) if item and item.get("tenant_id") == settings.effective_tenant_id else None

    def find_by_provider_id(self, provider_message_id: str) -> Optional[WhatsAppMessage]:
        if self._table is None:
            for item in self._memory.values():
                if item.tenant_id == settings.effective_tenant_id and item.provider_message_id == provider_message_id:
                    return item.model_copy(deep=True)
            return None
        response = self._table.query(
            IndexName="tenant-provider-message-index",
            KeyConditionExpression=Key("tenant_provider_message_id").eq(
                f"{settings.effective_tenant_id}#{provider_message_id}"
            ),
            Limit=1,
        )
        items = response.get("Items", [])
        return WhatsAppMessage(**items[0]) if items else None

    def list_for_lead(self, lead_id: str, limit: int = 50) -> list[WhatsAppMessage]:
        if self._table is None:
            items = [item for item in self._memory.values()
                     if item.tenant_id == settings.effective_tenant_id and item.lead_id == lead_id]
            return [item.model_copy(deep=True) for item in sorted(items, key=lambda row: row.created_at, reverse=True)[:limit]]
        response = self._table.query(
            IndexName="tenant-lead-created-index",
            KeyConditionExpression=Key("tenant_lead_key").eq(f"{settings.effective_tenant_id}#{lead_id}"),
            ScanIndexForward=False,
            Limit=limit,
        )
        return [WhatsAppMessage(**item) for item in response.get("Items", [])]

    def all_for_lead(self, lead_id: str) -> list[WhatsAppMessage]:
        if self._table is None:
            return self.list_for_lead(lead_id, limit=max(1, len(self._memory)))
        items = []
        query = {
            "IndexName": "tenant-lead-created-index",
            "KeyConditionExpression": Key("tenant_lead_key").eq(f"{settings.effective_tenant_id}#{lead_id}"),
            "ScanIndexForward": True,
        }
        while True:
            response = self._table.query(**query)
            items.extend(WhatsAppMessage(**item) for item in response.get("Items", []))
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                return items
            query["ExclusiveStartKey"] = last_key

    def create_attempt(self, message: WhatsAppMessage, audit: AuditEvent, audit_repo) -> tuple[WhatsAppMessage, bool]:
        message.tenant_lead_key = f"{settings.effective_tenant_id}#{message.lead_id}"
        if self._table is None:
            existing = self._memory.get(message.message_id)
            if existing:
                return existing.model_copy(deep=True), False
            self._memory[message.message_id] = message.model_copy(deep=True)
            audit_repo.store(audit)
            return message, True

        if audit_repo.use_memory or not audit_repo._table:
            raise RuntimeError("WhatsApp messages and audit must use the same persistent storage mode")
        try:
            self._table.meta.client.transact_write_items(TransactItems=[
                {"Put": {
                    "TableName": settings.whatsapp_messages_table,
                    "Item": _av(message.model_dump(mode="json")),
                    "ConditionExpression": "attribute_not_exists(message_id)",
                }},
                {"Put": {
                    "TableName": settings.audit_table,
                    "Item": _av(audit.model_dump(mode="json")),
                    "ConditionExpression": "attribute_not_exists(audit_id)",
                }},
            ])
            return message, True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "TransactionCanceledException":
                raise
            existing = self.get(message.message_id)
            if existing:
                return existing, False
            raise

    def apply_api_result(
        self,
        message_id: str,
        status: WhatsAppDeliveryStatus,
        audit: AuditEvent,
        audit_repo,
        provider_message_id: Optional[str] = None,
        error_code: Optional[str] = None,
    ) -> WhatsAppMessage:
        if self._table is None:
            current = self._memory.get(message_id)
            if not current:
                raise KeyError(message_id)
            if current.status == WhatsAppDeliveryStatus.SUBMITTING:
                current = current.model_copy(deep=True)
                current.status = status
                current.updated_at = now_iso()
                current.provider_message_id = provider_message_id
                current.tenant_provider_message_id = (
                    f"{settings.effective_tenant_id}#{provider_message_id}" if provider_message_id else None
                )
                current.error_code = error_code
                self._memory[message_id] = current
                audit_repo.store(audit)
            return current.model_copy(deep=True)

        if audit_repo.use_memory or not audit_repo._table:
            raise RuntimeError("WhatsApp messages and audit must use the same persistent storage mode")
        names = {"#status": "status"}
        values = {":submitting": "submitting", ":status": status.value, ":updated": now_iso(), ":tenant": settings.effective_tenant_id}
        update = "SET #status = :status, updated_at = :updated"
        if provider_message_id:
            update += ", provider_message_id = :provider_id, tenant_provider_message_id = :tenant_provider_id"
            values[":provider_id"] = provider_message_id
            values[":tenant_provider_id"] = f"{settings.effective_tenant_id}#{provider_message_id}"
        if error_code:
            update += ", error_code = :error_code"
            values[":error_code"] = error_code
        try:
            self._table.meta.client.transact_write_items(TransactItems=[
                {"Update": {
                    "TableName": settings.whatsapp_messages_table,
                    "Key": _av({"message_id": message_id}),
                    "UpdateExpression": update,
                    "ConditionExpression": "tenant_id = :tenant AND #status = :submitting",
                    "ExpressionAttributeNames": names,
                    "ExpressionAttributeValues": _av(values),
                }},
                {"Put": {
                    "TableName": settings.audit_table,
                    "Item": _av(audit.model_dump(mode="json")),
                    "ConditionExpression": "attribute_not_exists(audit_id)",
                }},
            ])
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "TransactionCanceledException":
                raise
            current = self.get(message_id)
            if current:
                return current
            raise
        return self.get(message_id)

    def apply_provider_status(
        self,
        message_id: str,
        provider_status: str,
        provider_message_id: str,
        event_timestamp: int,
        audit_repo,
        error_code: Optional[str] = None,
    ) -> Optional[WhatsAppMessage]:
        rank = _STATUS_RANK[provider_status]
        normalized = WhatsAppDeliveryStatus(provider_status)
        current = self.get(message_id)
        if not current:
            return None
        if current.provider_status_at is not None and (
            event_timestamp < current.provider_status_at
            or (event_timestamp == current.provider_status_at and rank <= current.provider_status_rank)
        ):
            return current

        audit = audit_repo.build(AuditEventCreate(
            lead_id=current.lead_id,
            action="whatsapp_provider_status",
            actor="provider:meta_whatsapp",
            details={
                "message_id": message_id,
                "provider_message_id": provider_message_id,
                "status": provider_status,
                "provider_timestamp": event_timestamp,
                "error_code": error_code,
            },
        ))
        updated_at = now_iso()
        if self._table is None:
            latest = self._memory.get(message_id)
            if not latest:
                return None
            if latest.provider_status_at is not None and (
                event_timestamp < latest.provider_status_at
                or (event_timestamp == latest.provider_status_at and rank <= latest.provider_status_rank)
            ):
                return latest.model_copy(deep=True)
            latest = latest.model_copy(deep=True)
            latest.status = normalized
            latest.provider_message_id = provider_message_id
            latest.tenant_provider_message_id = f"{settings.effective_tenant_id}#{provider_message_id}"
            latest.provider_status_at = event_timestamp
            latest.provider_status_rank = rank
            latest.error_code = error_code
            latest.updated_at = updated_at
            self._memory[message_id] = latest
            audit_repo.store(audit)
            return latest.model_copy(deep=True)

        condition = "tenant_id = :tenant AND (attribute_not_exists(provider_status_at) OR provider_status_at < :event_at OR (provider_status_at = :event_at AND provider_status_rank < :rank))"
        values = {":tenant": settings.effective_tenant_id, ":event_at": event_timestamp, ":rank": rank,
                  ":status": normalized.value, ":provider_id": provider_message_id,
                  ":tenant_provider_id": f"{settings.effective_tenant_id}#{provider_message_id}", ":updated": updated_at}
        update_expression = "SET #status = :status, provider_message_id = :provider_id, tenant_provider_message_id = :tenant_provider_id, provider_status_at = :event_at, provider_status_rank = :rank, updated_at = :updated"
        if error_code:
            update_expression += ", error_code = :error_code"
            values[":error_code"] = error_code
        else:
            update_expression += " REMOVE error_code"
        try:
            self._table.meta.client.transact_write_items(TransactItems=[
                {"Update": {
                    "TableName": settings.whatsapp_messages_table,
                    "Key": _av({"message_id": message_id}),
                    "UpdateExpression": update_expression,
                    "ConditionExpression": condition,
                    "ExpressionAttributeNames": {"#status": "status"},
                    "ExpressionAttributeValues": _av(values),
                }},
                {"Put": {
                    "TableName": settings.audit_table,
                    "Item": _av(audit.model_dump(mode="json")),
                    "ConditionExpression": "attribute_not_exists(audit_id)",
                }},
            ])
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "TransactionCanceledException":
                raise
        return self.get(message_id)


repository = WhatsAppMessagesRepository()
