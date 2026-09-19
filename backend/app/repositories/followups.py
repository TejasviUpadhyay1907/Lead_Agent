"""
LeadRescue AI — FollowUps Repository
Provides persistence for FollowUp records (DynamoDB & Memory fallback).
"""

from typing import Dict, List, Optional
from app.config.settings import settings
from app.models.followup import FollowUp, FollowUpCreate, FollowUpUpdate
from app.repositories.base import get_boto3_dynamodb_resource


class FollowUpsRepository:
    def __init__(self, use_memory: bool = False):
        self.use_memory = use_memory
        self._memory_store: Dict[str, FollowUp] = {}
        self._table = None

        if not use_memory:
            dynamodb = get_boto3_dynamodb_resource()
            if dynamodb and settings.followups_table:
                try:
                    self._table = dynamodb.Table(settings.followups_table)
                except Exception:
                    self.use_memory = True
            else:
                self.use_memory = True

    def create(self, followup_create: FollowUpCreate) -> FollowUp:
        followup = FollowUp(**followup_create.model_dump())
        if self.use_memory or not self._table:
            self._memory_store[followup.followup_id] = followup
            return followup
        try:
            self._table.put_item(Item=followup.model_dump())
            return followup
        except Exception:
            self._memory_store[followup.followup_id] = followup
            return followup

    def save(self, followup: FollowUp) -> FollowUp:
        if self.use_memory or not self._table:
            self._memory_store[followup.followup_id] = followup
            return followup
        try:
            self._table.put_item(Item=followup.model_dump())
            return followup
        except Exception:
            self._memory_store[followup.followup_id] = followup
            return followup

    def get_by_id(self, followup_id: str) -> Optional[FollowUp]:
        if self.use_memory or not self._table:
            return self._memory_store.get(followup_id)
        try:
            response = self._table.get_item(Key={"followup_id": followup_id})
            item = response.get("Item")
            if item:
                return FollowUp(**item)
            return self._memory_store.get(followup_id)
        except Exception:
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
                response = self._table.scan()
                items = response.get("Items", [])
                fups = [FollowUp(**item) for item in items]
            except Exception:
                fups = list(self._memory_store.values())

        if lead_id:
            fups = [f for f in fups if f.lead_id == lead_id]
        if status:
            fups = [f for f in fups if f.status == status]

        fups.sort(key=lambda x: x.due_at)
        return fups

    def update(self, followup_id: str, followup_update: FollowUpUpdate) -> Optional[FollowUp]:
        followup = self.get_by_id(followup_id)
        if not followup:
            return None

        update_data = followup_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                setattr(followup, key, value)

        return self.save(followup)
