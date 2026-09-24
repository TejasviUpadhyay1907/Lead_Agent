"""Durable, PII-minimized WhatsApp delivery state."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.config.settings import settings


class WhatsAppDeliveryStatus(str, Enum):
    SUBMITTING = "submitting"
    ACCEPTED = "accepted"
    UNKNOWN = "unknown"
    FAILED = "failed"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class WhatsAppMessage(BaseModel):
    message_id: str = Field(..., min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    tenant_id: str = Field(default_factory=lambda: settings.effective_tenant_id)
    lead_id: str
    tenant_lead_key: Optional[str] = None
    status: WhatsAppDeliveryStatus
    initiated_by: str
    approved_draft_sha256: str = Field(..., pattern=r"^[a-f0-9]{64}$")
    approval_attested_at: str
    template_body_sha256: str = Field(..., pattern=r"^[a-f0-9]{64}$")
    template_fingerprint: str = Field(..., pattern=r"^[a-f0-9]{64}$")
    rendered_message_sha256: str = Field(..., pattern=r"^[a-f0-9]{64}$")
    rendered_message: str = Field(..., min_length=1, max_length=1024)
    consent_evidence_ref: str
    recipient_phone_key: str
    template_name: str
    template_language: str
    provider_api_version: str
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    provider_message_id: Optional[str] = None
    tenant_provider_message_id: Optional[str] = None
    provider_status_at: Optional[int] = None
    provider_status_rank: int = 0
    error_code: Optional[str] = None

    model_config = ConfigDict(extra="ignore", from_attributes=True)

