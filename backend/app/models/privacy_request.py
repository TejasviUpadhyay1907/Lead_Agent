"""Metadata-only customer privacy request tracking."""

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.config.settings import settings


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PrivacyRequestType(str, Enum):
    ACCESS = "access"
    ERASURE = "erasure"


class PrivacyRequestStatus(str, Enum):
    PENDING_ADMIN_REVIEW = "pending_admin_review"
    IDENTITY_VERIFICATION_REQUIRED = "identity_verification_required"
    VERIFIED = "verified"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"


class PrivacyRequest(BaseModel):
    """A tenant-scoped pointer to a lead; contact data stays on the lead record."""

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = Field(default_factory=lambda: settings.effective_tenant_id)
    lead_id: str
    request_type: PrivacyRequestType
    source: str = Field(..., pattern=r"^(manual|integration:[a-zA-Z0-9_.-]{1,64})$")
    status: PrivacyRequestStatus = PrivacyRequestStatus.PENDING_ADMIN_REVIEW
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    tenant_status: str = ""
    tenant_queue: str = ""
    reviewer: str | None = None
    verified_by: str | None = None
    completed_by: str | None = None
    resolution_code: str | None = None

    model_config = ConfigDict(extra="forbid")

    def model_post_init(self, __context) -> None:
        self.tenant_status = f"{self.tenant_id}#{self.status.value}"
        bucket = "closed" if self.status in {PrivacyRequestStatus.COMPLETED, PrivacyRequestStatus.REJECTED} else "open"
        self.tenant_queue = f"{self.tenant_id}#{bucket}"


class PrivacyRequestStatusUpdate(BaseModel):
    status: PrivacyRequestStatus
    resolution_code: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{1,63}$")

    model_config = ConfigDict(extra="forbid")
