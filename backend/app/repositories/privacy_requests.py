"""Tenant-scoped privacy request queue repository."""

from typing import Dict, Optional, Tuple

from boto3.dynamodb.conditions import Key
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

from app.config.settings import settings
from app.models.audit import AuditEvent
from app.models.privacy_request import PrivacyRequest, PrivacyRequestStatus
from app.repositories.base import get_boto3_dynamodb_resource
from app.repositories.pagination import decode_cursor, encode_cursor


class ConcurrentPrivacyRequestUpdateError(Exception):
    """Raised when another admin changes a privacy request first."""


def _serialize(item: dict) -> dict:
    serializer = TypeSerializer()
    return {key: serializer.serialize(value) for key, value in item.items()}


class PrivacyRequestsRepository:
    def __init__(self, use_memory: bool = False):
        self.use_memory = use_memory or settings.demo_enabled
        self._memory_store: Dict[str, PrivacyRequest] = {}
        self._table = None
        if not self.use_memory:
            dynamodb = get_boto3_dynamodb_resource()
            if not dynamodb or not settings.privacy_requests_table:
                raise RuntimeError("Privacy request storage is required when DEMO_MODE is disabled")
            self._table = dynamodb.Table(settings.privacy_requests_table)

    def create(self, request: PrivacyRequest) -> PrivacyRequest:
        if self.use_memory or not self._table:
            self._memory_store[request.request_id] = request
            return request
        self._table.put_item(
            Item=request.model_dump(mode="json"),
            ConditionExpression="attribute_not_exists(request_id)",
        )
        return request

    def get_by_id(self, request_id: str) -> Optional[PrivacyRequest]:
        if self.use_memory or not self._table:
            request = self._memory_store.get(request_id)
            if request:
                request = request.model_copy(deep=True)
        else:
            request = self._table.get_item(Key={"request_id": request_id}, ConsistentRead=True).get("Item")
            if request and request.get("tenant_id") != settings.effective_tenant_id:
                return None
            if request:
                request = PrivacyRequest(**request)
        return request if request and request.tenant_id == settings.effective_tenant_id else None

    def list_page(
        self,
        limit: int = 50,
        cursor: Optional[str] = None,
        status: Optional[PrivacyRequestStatus | str] = None,
    ) -> Tuple[list[PrivacyRequest], Optional[str]]:
        status_value = status.value if isinstance(status, PrivacyRequestStatus) else status
        filters = {"tenant_id": settings.effective_tenant_id, "status": status_value}
        state = decode_cursor(cursor, filters, {"tenant_id", "tenant_status", "tenant_queue", "created_at", "request_id"})
        if self.use_memory or not self._table:
            rows = [item for item in self._memory_store.values() if item.tenant_id == settings.effective_tenant_id]
            if status_value in {"open", "closed"}:
                closed_statuses = {PrivacyRequestStatus.COMPLETED, PrivacyRequestStatus.REJECTED}
                rows = [item for item in rows if (item.status in closed_statuses) == (status_value == "closed")]
            elif status_value:
                rows = [item for item in rows if item.status.value == status_value]
            rows.sort(key=lambda item: (item.created_at, item.request_id), reverse=True)
            offset = state.get("offset", 0)
            page = rows[offset:offset + limit]
            next_cursor = encode_cursor({"offset": offset + len(page), "filter": filters}) if offset + len(page) < len(rows) else None
            return page, next_cursor

        if status_value in {"open", "closed"}:
            partition_key = f"{settings.effective_tenant_id}#{status_value}"
            index = "tenant-queue-created-index"
            key_condition = Key("tenant_queue").eq(partition_key)
        elif status_value:
            partition_key = f"{settings.effective_tenant_id}#{status_value}"
            index = "tenant-status-created-index"
            key_condition = Key("tenant_status").eq(partition_key)
        else:
            index = "tenant-created-index"
            key_condition = Key("tenant_id").eq(settings.effective_tenant_id)
        query = {
            "IndexName": index,
            "KeyConditionExpression": key_condition,
            "ScanIndexForward": False,
            "Limit": limit,
        }
        if state.get("last_key"):
            query["ExclusiveStartKey"] = state["last_key"]
        response = self._table.query(**query)
        page = [PrivacyRequest(**item) for item in response.get("Items", [])]
        last_key = response.get("LastEvaluatedKey")
        next_cursor = encode_cursor({"last_key": last_key, "filter": filters}) if last_key else None
        return page, next_cursor

    def save_with_audit(
        self,
        request: PrivacyRequest,
        audit: AuditEvent,
        audit_repo,
        expected_status: PrivacyRequestStatus,
    ) -> PrivacyRequest:
        if self.use_memory or not self._table:
            if not audit_repo.use_memory:
                raise RuntimeError("Privacy requests and audit must use the same persistence mode")
            current = self._memory_store.get(request.request_id)
            if not current or current.status != expected_status or current.tenant_id != settings.effective_tenant_id:
                raise ConcurrentPrivacyRequestUpdateError("Privacy request changed or was not found")
            self._memory_store[request.request_id] = request
            audit_repo.store(audit)
            return request
        if audit_repo.use_memory or not audit_repo._table:
            raise RuntimeError("Privacy requests and audit must use the same persistence mode")
        try:
            self._table.meta.client.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": settings.privacy_requests_table,
                            "Item": _serialize(request.model_dump(mode="json")),
                            "ConditionExpression": "#tenant = :tenant AND #status = :expected",
                            "ExpressionAttributeNames": {"#tenant": "tenant_id", "#status": "status"},
                            "ExpressionAttributeValues": _serialize({
                                ":tenant": settings.effective_tenant_id,
                                ":expected": expected_status.value,
                            }),
                        }
                    },
                    {
                        "Put": {
                            "TableName": settings.audit_table,
                            "Item": _serialize(audit.model_dump(mode="json")),
                            "ConditionExpression": "attribute_not_exists(audit_id)",
                        }
                    },
                ]
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "TransactionCanceledException":
                raise ConcurrentPrivacyRequestUpdateError("Privacy request changed after it was loaded") from exc
            raise
        return request
