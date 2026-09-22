"""
LeadRescue AI — FollowUp Domain Model
Strict Pydantic model for Follow-up tasks.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.config.settings import settings

from app.models.enums import FollowUpStatusEnum


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FollowUpBase(BaseModel):
    lead_id: str
    action: str = Field(..., min_length=1)
    due_at: str
    status: FollowUpStatusEnum = FollowUpStatusEnum.SCHEDULED
    notes: Optional[str] = None


class FollowUpCreate(FollowUpBase):
    model_config = ConfigDict(extra="forbid")


class FollowUpUpdate(BaseModel):
    status: Optional[FollowUpStatusEnum] = None
    completed_at: Optional[str] = None
    notes: Optional[str] = None
    model_config = ConfigDict(extra="forbid")


class FollowUp(FollowUpBase):
    followup_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = Field(default_factory=lambda: settings.effective_tenant_id)
    created_at: str = Field(default_factory=utc_now_iso)
    completed_at: Optional[str] = None

    model_config = ConfigDict(extra="ignore", from_attributes=True)
