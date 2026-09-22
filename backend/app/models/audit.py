"""
LeadRescue AI — Audit Domain Model
Strict Pydantic model for Audit trail records.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict
from pydantic import BaseModel, ConfigDict, Field
from app.config.settings import settings


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditEventCreate(BaseModel):
    lead_id: str
    action: str = Field(..., min_length=1)
    actor: str = Field(..., min_length=1)  # "system", "agent", "user:{name}"
    details: Dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(extra="forbid")


class AuditEvent(AuditEventCreate):
    audit_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = Field(default_factory=lambda: settings.effective_tenant_id)
    tenant_lead_id: str = ""
    timestamp: str = Field(default_factory=utc_now_iso)

    model_config = ConfigDict(extra="ignore", from_attributes=True)
