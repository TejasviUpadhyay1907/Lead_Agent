"""
LeadRescue AI — Lead Domain Model
Strict Pydantic model for Lead records according to Phase 0 Revision 3.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.config.settings import settings

from app.models.enums import (
    CustomerStageEnum,
    IntentEnum,
    LifecycleStatusEnum,
    PriorityEnum,
    ResponseStatusEnum,
    RiskStatusEnum,
    SourceEnum,
    UrgencyEnum,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LeadBase(BaseModel):
    customer_name: str = Field(..., min_length=1, max_length=200)
    customer_email: Optional[EmailStr] = None
    customer_phone: Optional[str] = Field(default=None, max_length=64)
    source: SourceEnum = SourceEnum.WEBSITE
    raw_message: str = Field(..., min_length=1, max_length=20000)
    assigned_to: Optional[str] = None


class LeadCreate(LeadBase):
    """Payload for creating a new Lead via POST /api/leads"""
    # Note: Deterministic & AI fields CANNOT be set at creation by clients
    model_config = ConfigDict(extra="forbid")


class LeadUpdate(BaseModel):
    """Payload for updating Lead lifecycle or response status"""
    customer_name: Optional[str] = None
    customer_email: Optional[EmailStr] = None
    customer_phone: Optional[str] = None
    assigned_to: Optional[str] = None
    lifecycle_status: Optional[LifecycleStatusEnum] = None
    response_status: Optional[ResponseStatusEnum] = None
    last_analysis_job_id: Optional[str] = None
    response_draft: Optional[str] = None
    model_config = ConfigDict(extra="forbid")


class Lead(LeadBase):
    """Full Lead domain model stored in DynamoDB"""
    lead_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = Field(default_factory=lambda: settings.effective_tenant_id)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)

    # AI Extracted Fields (Populated by Strands Agent in Phase 3)
    intent: Optional[IntentEnum] = None
    urgency: Optional[UrgencyEnum] = None
    product: Optional[str] = None
    quantity: Optional[int] = Field(default=None, ge=0)
    location: Optional[str] = None
    customer_stage: Optional[CustomerStageEnum] = None
    key_entities: List[str] = Field(default_factory=list)
    ai_summary: Optional[str] = None
    recommended_action: Optional[str] = None
    response_draft: Optional[str] = None

    # Deterministic Engine Calculated Fields (Populated in Phase 4)
    score: Optional[int] = Field(default=None, ge=0, le=100)
    score_breakdown: Dict[str, int] = Field(default_factory=dict)
    priority: Optional[PriorityEnum] = None

    # Status Concepts (Orthogonal)
    lifecycle_status: LifecycleStatusEnum = LifecycleStatusEnum.NEW
    risk_status: RiskStatusEnum = RiskStatusEnum.NORMAL
    at_risk_at: Optional[str] = None

    # Response Status (Human Approval Workflow)
    response_status: Optional[ResponseStatusEnum] = None

    model_config = ConfigDict(extra="ignore", from_attributes=True)
