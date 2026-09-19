"""
LeadRescue AI — Audit Repository
Provides persistence for AuditEvent records (DynamoDB & Memory fallback).
"""

from typing import Dict, List, Optional
from app.config.settings import settings
from app.models.audit import AuditEvent, AuditEventCreate
from app.repositories.base import get_boto3_dynamodb_resource


class AuditRepository:
    def __init__(self, use_memory: bool = False):
        self.use_memory = use_memory
        self._memory_store: Dict[str, AuditEvent] = {}
        self._table = None

        if not use_memory:
            dynamodb = get_boto3_dynamodb_resource()
            if dynamodb and settings.audit_table:
                try:
                    self._table = dynamodb.Table(settings.audit_table)
                except Exception:
                    self.use_memory = True
            else:
                self.use_memory = True

    def create(self, audit_create: AuditEventCreate) -> AuditEvent:
        audit = AuditEvent(**audit_create.model_dump())
        if self.use_memory or not self._table:
            self._memory_store[audit.audit_id] = audit
            return audit
        try:
            self._table.put_item(Item=audit.model_dump())
            return audit
        except Exception:
            self._memory_store[audit.audit_id] = audit
            return audit

    def list_by_lead(self, lead_id: str) -> List[AuditEvent]:
        if self.use_memory or not self._table:
            events = [e for e in self._memory_store.values() if e.lead_id == lead_id]
        else:
            try:
                response = self._table.scan()
                items = response.get("Items", [])
                events = [AuditEvent(**item) for item in items if item.get("lead_id") == lead_id]
            except Exception:
                events = [e for e in self._memory_store.values() if e.lead_id == lead_id]

        events.sort(key=lambda x: x.timestamp)
        return events
