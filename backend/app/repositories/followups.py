"""
LeadRescue AI — FollowUps Repository
Provides persistence for FollowUp records (DynamoDB & Memory fallback).
"""

from typing import Dict, List, Optional
from botocore.exceptions import ClientError
from boto3.dynamodb.types import TypeSerializer
from boto3.dynamodb.conditions import Attr, Key
from app.config.settings import settings
from app.models.followup import FollowUp, FollowUpCreate, FollowUpUpdate
from app.models.audit import AuditEvent
from app.repositories.base import get_boto3_dynamodb_resource
from app.repositories.pagination import decode_cursor, encode_cursor


class ConcurrentFollowupUpdateError(Exception):
    """Raised when a follow-up has changed since it was loaded."""


def _serialize_item(item: dict) -> dict:
    serializer = TypeSerializer()
    return {key: serializer.serialize(value) for key, value in item.items()}


class FollowUpsRepository:
    def __init__(self, use_memory: bool = False):
        self.use_memory = use_memory or settings.demo_enabled
        self._memory_store: Dict[str, FollowUp] = {}
        self._table = None

        if not self.use_memory:
            dynamodb = get_boto3_dynamodb_resource()
            if dynamodb and settings.followups_table:
                try:
                    self._table = dynamodb.Table(settings.followups_table)
                except Exception:
                    if not settings.demo_enabled:
                        raise
                    self.use_memory = True
            else:
                if not settings.demo_enabled:
                    raise RuntimeError("DynamoDB is required when DEMO_MODE is disabled")
                self.use_memory = True

    def create(self, followup_create: FollowUpCreate) -> FollowUp:
        followup = FollowUp(**followup_create.model_dump())
        if self.use_memory or not self._table:
            self._memory_store[followup.followup_id] = followup
            return followup
        try:
            self._table.put_item(Item=followup.model_dump(), ConditionExpression=Attr("followup_id").not_exists())
            return followup
        except Exception:
            if not settings.demo_enabled:
                raise
            self._memory_store[followup.followup_id] = followup
            return followup

    def save(self, followup: FollowUp) -> FollowUp:
        if self.use_memory or not self._table:
            self._memory_store[followup.followup_id] = followup
            return followup
        try:
            self._table.put_item(Item=followup.model_dump(), ConditionExpression=Attr("tenant_id").eq(settings.effective_tenant_id))
            return followup
        except Exception:
            if not settings.demo_enabled:
                raise
            self._memory_store[followup.followup_id] = followup
            return followup

    def save_with_audit(self, followup: FollowUp, audit: AuditEvent, audit_repo, expected_status) -> FollowUp:
        """Atomically persist a follow-up status change and its audit event."""
        if self.use_memory or not self._table:
            if not audit_repo.use_memory:
                raise RuntimeError("Follow-up and audit records must use the same persistent storage mode")
            self._memory_store[followup.followup_id] = followup
            audit_repo.store(audit)
            return followup
        if audit_repo.use_memory or not audit_repo._table:
            raise RuntimeError("Follow-up and audit records must use the same persistent storage mode")

        try:
            self._table.meta.client.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": settings.followups_table,
                            "Item": _serialize_item(followup.model_dump(mode="json")),
                            "ConditionExpression": "#tenant = :tenant AND #status = :expected",
                            "ExpressionAttributeNames": {"#tenant": "tenant_id", "#status": "status"},
                            "ExpressionAttributeValues": {
                                ":tenant": _serialize_item({"v": settings.effective_tenant_id})["v"],
                                ":expected": _serialize_item({"v": expected_status.value})["v"],
                            },
                        }
                    },
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
                raise ConcurrentFollowupUpdateError("Follow-up changed after it was loaded") from exc
            raise
        return followup

    def get_by_id(self, followup_id: str) -> Optional[FollowUp]:
        if self.use_memory or not self._table:
            return self._memory_store.get(followup_id)
        try:
            response = self._table.get_item(Key={"followup_id": followup_id})
            item = response.get("Item")
            if item and item.get("tenant_id") == settings.effective_tenant_id:
                return FollowUp(**item)
            return None
        except Exception:
            if not settings.demo_enabled:
                raise
            return self._memory_store.get(followup_id)

    def list_followups(
        self,
        lead_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[FollowUp]:
        if self.use_memory or not self._table:
            fups = list(self._memory_store.values())
        else:
            try:
                fups = []
                query_args = {
                    "IndexName": "tenant-due-index",
                    "KeyConditionExpression": Key("tenant_id").eq(settings.effective_tenant_id),
                    "ScanIndexForward": True,
                }
                while True:
                    response = self._table.query(**query_args)
                    fups.extend(FollowUp(**item) for item in response.get("Items", []))
                    last_key = response.get("LastEvaluatedKey")
                    if not last_key:
                        break
                    query_args["ExclusiveStartKey"] = last_key
            except Exception:
                if not settings.demo_enabled:
                    raise
                fups = list(self._memory_store.values())

        if lead_id:
            fups = [f for f in fups if f.lead_id == lead_id]
        if status:
            fups = [f for f in fups if f.status == status]

        fups.sort(key=lambda x: x.due_at)
        return fups

    def list_followups_page(
        self,
        limit: int = 50,
        cursor: Optional[str] = None,
        lead_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> tuple[List[FollowUp], Optional[str]]:
        """Read one bounded page and return an opaque continuation cursor."""
        filters = {"tenant_id": settings.effective_tenant_id, "lead_id": lead_id, "status": status}
        state = decode_cursor(cursor, filters, {"tenant_id", "due_at", "followup_id"})

        if self.use_memory or not self._table:
            fups = list(self._memory_store.values())
            if lead_id:
                fups = [item for item in fups if item.lead_id == lead_id]
            if status:
                fups = [item for item in fups if item.status == status]
            fups.sort(key=lambda item: item.due_at)
            offset = int(state.get("offset", 0))
            page = fups[offset:offset + limit]
            next_cursor = encode_cursor({"offset": offset + len(page), "filter": filters}) if offset + len(page) < len(fups) else None
            return page, next_cursor

        conditions = []
        if lead_id:
            conditions.append(Attr("lead_id").eq(lead_id))
        if status:
            conditions.append(Attr("status").eq(status))
        filter_expression = None
        for condition in conditions:
            filter_expression = condition if filter_expression is None else filter_expression & condition
        query_args = {
            "IndexName": "tenant-due-index",
            "KeyConditionExpression": Key("tenant_id").eq(settings.effective_tenant_id),
            "ScanIndexForward": True,
            "Limit": limit,
        }
        if state.get("last_key"):
            query_args["ExclusiveStartKey"] = state["last_key"]
        if filter_expression is not None:
            query_args["FilterExpression"] = filter_expression
        try:
            response = self._table.query(**query_args)
        except Exception:
            if not settings.demo_enabled:
                raise
            self.use_memory = True
            return self.list_followups_page(limit=limit, lead_id=lead_id, status=status)
        page = [FollowUp(**item) for item in response.get("Items", [])]
        page.sort(key=lambda item: item.due_at)
        last_key = response.get("LastEvaluatedKey")
        next_cursor = encode_cursor({"last_key": last_key, "filter": filters}) if last_key else None
        return page, next_cursor

    def update(self, followup_id: str, followup_update: FollowUpUpdate) -> Optional[FollowUp]:
        followup = self.get_by_id(followup_id)
        if not followup:
            return None

        update_data = followup_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                setattr(followup, key, value)

        return self.save(followup)
