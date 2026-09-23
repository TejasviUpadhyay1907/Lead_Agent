"""
LeadRescue AI — Audit Repository
Provides persistence for AuditEvent records (DynamoDB & Memory fallback).
"""

from typing import Dict, List, Optional, Tuple
from boto3.dynamodb.conditions import Key
from app.config.settings import settings
from app.models.audit import AuditEvent, AuditEventCreate
from app.repositories.base import get_boto3_dynamodb_resource
from app.repositories.pagination import decode_cursor, encode_cursor


class AuditRepository:
    def __init__(self, use_memory: bool = False):
        self.use_memory = use_memory or settings.demo_enabled
        self._memory_store: Dict[str, AuditEvent] = {}
        self._table = None

        if not self.use_memory:
            dynamodb = get_boto3_dynamodb_resource()
            if dynamodb and settings.audit_table:
                try:
                    self._table = dynamodb.Table(settings.audit_table)
                except Exception:
                    if not settings.demo_enabled:
                        raise
                    self.use_memory = True
            else:
                if not settings.demo_enabled:
                    raise RuntimeError("DynamoDB is required when DEMO_MODE is disabled")
                self.use_memory = True

    def create(self, audit_create: AuditEventCreate) -> AuditEvent:
        audit = self.build(audit_create)
        return self.store(audit)

    def build(self, audit_create: AuditEventCreate) -> AuditEvent:
        """Build an event with the tenant keys used by persistent and in-memory stores."""
        return AuditEvent(
            **audit_create.model_dump(),
            tenant_id=settings.effective_tenant_id,
            tenant_lead_id=f"{settings.effective_tenant_id}#{audit_create.lead_id}",
        )

    def store(self, audit: AuditEvent) -> AuditEvent:
        """Persist one audit event outside a coordinated transaction."""
        if self.use_memory or not self._table:
            self._memory_store[audit.audit_id] = audit
            return audit
        try:
            self._table.put_item(Item=audit.model_dump())
            return audit
        except Exception:
            if not settings.demo_enabled:
                raise
            self._memory_store[audit.audit_id] = audit
            return audit

    def list_by_lead(self, lead_id: str) -> List[AuditEvent]:
        if self.use_memory or not self._table:
            events = [e for e in self._memory_store.values() if e.lead_id == lead_id and e.tenant_id == settings.effective_tenant_id]
        else:
            try:
                events = []
                query_args = {
                    "IndexName": "tenant-lead-timestamp-index",
                    "KeyConditionExpression": Key("tenant_lead_id").eq(f"{settings.effective_tenant_id}#{lead_id}"),
                    "ScanIndexForward": True,
                }
                while True:
                    response = self._table.query(**query_args)
                    events.extend(AuditEvent(**item) for item in response.get("Items", []))
                    last_key = response.get("LastEvaluatedKey")
                    if not last_key:
                        break
                    query_args["ExclusiveStartKey"] = last_key
            except Exception:
                if not settings.demo_enabled:
                    raise
                events = [e for e in self._memory_store.values() if e.lead_id == lead_id]

        events.sort(key=lambda x: x.timestamp)
        return events

    def list_by_lead_page(self, lead_id: str, limit: int = 50, cursor: Optional[str] = None) -> Tuple[List[AuditEvent], Optional[str]]:
        """Return a bounded, chronological page of one tenant-scoped lead's audit events."""
        filters = {"tenant_id": settings.effective_tenant_id, "lead_id": lead_id}
        state = decode_cursor(cursor, filters, {"tenant_lead_id", "timestamp", "audit_id"})
        if self.use_memory or not self._table:
            events = [e for e in self._memory_store.values() if e.lead_id == lead_id and e.tenant_id == settings.effective_tenant_id]
            events.sort(key=lambda event: (event.timestamp, event.audit_id))
            offset = state.get("offset", 0)
            page = events[offset:offset + limit]
            next_cursor = encode_cursor({"offset": offset + len(page), "filter": filters}) if offset + len(page) < len(events) else None
            return page, next_cursor

        query_args = {
            "IndexName": "tenant-lead-timestamp-index",
            "KeyConditionExpression": Key("tenant_lead_id").eq(f"{settings.effective_tenant_id}#{lead_id}"),
            "ScanIndexForward": True,
            "Limit": limit,
        }
        if state.get("last_key"):
            query_args["ExclusiveStartKey"] = state["last_key"]
        response = self._table.query(**query_args)
        page = [AuditEvent(**item) for item in response.get("Items", [])]
        last_key = response.get("LastEvaluatedKey")
        next_cursor = encode_cursor({"last_key": last_key, "filter": filters}) if last_key else None
        return page, next_cursor
