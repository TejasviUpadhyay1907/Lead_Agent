"""
LeadRescue AI — Leads Repository
Provides persistence operations for Lead records (DynamoDB & Memory fallback).
"""

from typing import Dict, List, Optional
from app.config.settings import settings
from app.models.lead import Lead, LeadCreate, LeadUpdate
from app.repositories.base import get_boto3_dynamodb_resource


class LeadsRepository:
    """Repository for Lead operations."""

    def __init__(self, use_memory: bool = False):
        self.use_memory = use_memory
        self._memory_store: Dict[str, Lead] = {}
        self._table = None

        if not use_memory:
            dynamodb = get_boto3_dynamodb_resource()
            if dynamodb and settings.leads_table:
                try:
                    self._table = dynamodb.Table(settings.leads_table)
                except Exception:
                    self.use_memory = True
            else:
                self.use_memory = True

    def create(self, lead_create: LeadCreate) -> Lead:
        lead = Lead(**lead_create.model_dump())
        if self.use_memory or not self._table:
            self._memory_store[lead.lead_id] = lead
            return lead
        try:
            self._table.put_item(Item=lead.model_dump())
            return lead
        except Exception:
            # Fallback to memory if AWS fails
            self._memory_store[lead.lead_id] = lead
            return lead

    def get_by_id(self, lead_id: str) -> Optional[Lead]:
        if self.use_memory or not self._table:
            return self._memory_store.get(lead_id)
        try:
            response = self._table.get_item(Key={"lead_id": lead_id})
            item = response.get("Item")
            if item:
                return Lead(**item)
            return self._memory_store.get(lead_id)
        except Exception:
            return self._memory_store.get(lead_id)

    def list_leads(
        self,
        lifecycle_status: Optional[str] = None,
        priority: Optional[str] = None,
        risk_status: Optional[str] = None,
        source: Optional[str] = None,
    ) -> List[Lead]:
        if self.use_memory or not self._table:
            leads = list(self._memory_store.values())
        else:
            try:
                response = self._table.scan()
                items = response.get("Items", [])
                leads = [Lead(**item) for item in items]
            except Exception:
                leads = list(self._memory_store.values())

        # Filtering logic
        filtered = leads
        if lifecycle_status:
            filtered = [l for l in filtered if l.lifecycle_status == lifecycle_status]
        if priority:
            filtered = [l for l in filtered if l.priority == priority]
        if risk_status:
            filtered = [l for l in filtered if l.risk_status == risk_status]
        if source:
            filtered = [l for l in filtered if l.source == source]

        # Sort newest first
        filtered.sort(key=lambda x: x.created_at, reverse=True)
        return filtered

    def update(self, lead_id: str, lead_update: LeadUpdate) -> Optional[Lead]:
        lead = self.get_by_id(lead_id)
        if not lead:
            return None

        update_data = lead_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                setattr(lead, key, value)

        lead.updated_at = lead.model_dump().get("updated_at", lead.created_at)

        if self.use_memory or not self._table:
            self._memory_store[lead_id] = lead
            return lead

        try:
            self._table.put_item(Item=lead.model_dump())
            return lead
        except Exception:
            self._memory_store[lead_id] = lead
            return lead

    def save(self, lead: Lead) -> Lead:
        """Direct save for full lead object (used by internal services)."""
        if self.use_memory or not self._table:
            self._memory_store[lead.lead_id] = lead
            return lead
        try:
            self._table.put_item(Item=lead.model_dump())
            return lead
        except Exception:
            self._memory_store[lead.lead_id] = lead
            return lead
