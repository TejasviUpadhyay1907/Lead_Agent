"""Company-admin data export for an individual lead record."""

import json
import re
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from app.api.deps import get_audit_repo, get_followups_repo, get_leads_repo, get_privacy_requests_repo, get_whatsapp_messages_repo
from app.api.security import require_roles
from app.config.settings import settings
from app.models.audit import AuditEventCreate
from app.models.privacy_request import (
    PrivacyRequest,
    PrivacyRequestStatus,
    PrivacyRequestStatusUpdate,
)
from app.repositories.audit import AuditRepository
from app.repositories.followups import FollowUpsRepository
from app.repositories.leads import LeadsRepository
from app.repositories.privacy_requests import (
    ConcurrentPrivacyRequestUpdateError,
    PrivacyRequestsRepository,
)
from app.repositories.whatsapp_messages import WhatsAppMessagesRepository

router = APIRouter(prefix="/privacy", tags=["Privacy"])


class PrivacyRecordMatch(BaseModel):
    """Minimal candidate record; contact details and message content stay private."""

    lead_id: str
    created_at: str
    source: str
    lifecycle_status: str

    model_config = ConfigDict(extra="forbid")

_ALLOWED_TRANSITIONS = {
    PrivacyRequestStatus.PENDING_ADMIN_REVIEW: {
        PrivacyRequestStatus.IDENTITY_VERIFICATION_REQUIRED,
    },
    PrivacyRequestStatus.IDENTITY_VERIFICATION_REQUIRED: {
        PrivacyRequestStatus.VERIFIED,
        PrivacyRequestStatus.REJECTED,
    },
    PrivacyRequestStatus.VERIFIED: {
        PrivacyRequestStatus.IN_PROGRESS,
    },
    PrivacyRequestStatus.IN_PROGRESS: {
        PrivacyRequestStatus.COMPLETED,
    },
    PrivacyRequestStatus.COMPLETED: set(),
    PrivacyRequestStatus.REJECTED: set(),
}


@router.get("/requests", response_model=list[PrivacyRequest], summary="List privacy requests")
def list_privacy_requests(
    response: Response,
    _admin=Depends(require_roles(settings.admin_role)),
    request_status: PrivacyRequestStatus | Literal["open", "closed"] | None = Query(default="open", alias="status"),
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=4096),
    privacy_repo: PrivacyRequestsRepository = Depends(get_privacy_requests_repo),
):
    requests, next_cursor = privacy_repo.list_page(limit, cursor, request_status)
    if next_cursor:
        response.headers["X-Next-Cursor"] = next_cursor
    return requests


@router.put("/requests/{request_id}/status", response_model=PrivacyRequest, summary="Advance a privacy request")
def update_privacy_request_status(
    request_id: str,
    update: PrivacyRequestStatusUpdate,
    _admin=Depends(require_roles(settings.admin_role)),
    privacy_repo: PrivacyRequestsRepository = Depends(get_privacy_requests_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
):
    request = privacy_repo.get_by_id(request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Privacy request not found")
    if update.status not in _ALLOWED_TRANSITIONS[request.status]:
        raise HTTPException(status_code=409, detail="Privacy request status transition is not allowed")
    if update.status == PrivacyRequestStatus.COMPLETED:
        allowed_completion_codes = (
            {"access_provided", "no_data_found"}
            if request.request_type.value == "access"
            else {"erasure_completed", "no_data_found"}
        )
        if update.resolution_code not in allowed_completion_codes:
            raise HTTPException(status_code=422, detail="Completion code does not match the privacy request type")
    if update.status == PrivacyRequestStatus.REJECTED and update.resolution_code != "identity_not_verified":
        raise HTTPException(status_code=422, detail="Rejection requires the identity_not_verified code")
    if update.status == PrivacyRequestStatus.REJECTED and request.status != PrivacyRequestStatus.IDENTITY_VERIFICATION_REQUIRED:
        raise HTTPException(status_code=409, detail="A request can only be rejected during identity verification")
    if update.status not in {PrivacyRequestStatus.COMPLETED, PrivacyRequestStatus.REJECTED} and update.resolution_code is not None:
        raise HTTPException(status_code=422, detail="Completion code is only valid when closing a request")

    previous_status = request.status
    request.status = update.status
    request.tenant_status = f"{request.tenant_id}#{request.status.value}"
    request.tenant_queue = f"{request.tenant_id}#{'closed' if update.status in {PrivacyRequestStatus.COMPLETED, PrivacyRequestStatus.REJECTED} else 'open'}"
    request.updated_at = datetime.now(timezone.utc).isoformat()
    request.reviewer = _admin["sub"]
    if update.status == PrivacyRequestStatus.VERIFIED:
        request.verified_by = _admin["sub"]
    if update.status == PrivacyRequestStatus.COMPLETED:
        request.completed_by = _admin["sub"]
    request.resolution_code = update.resolution_code
    audit = audit_repo.build(
        AuditEventCreate(
            lead_id=request.lead_id,
            action="privacy_request_status_changed",
            actor=f"user:{_admin['sub']}",
            details={
                "privacy_request_id": request.request_id,
                "request_type": request.request_type.value,
                "previous_status": previous_status.value,
                "new_status": request.status.value,
                "resolution_code": request.resolution_code,
            },
        )
    )
    try:
        return privacy_repo.save_with_audit(request, audit, audit_repo, previous_status)
    except ConcurrentPrivacyRequestUpdateError as exc:
        raise HTTPException(status_code=409, detail="Privacy request changed; refresh and try again") from exc


@router.get(
    "/requests/{request_id}/records",
    response_model=list[PrivacyRecordMatch],
    summary="Discover records matching a verified privacy-request contact",
)
def discover_privacy_request_records(
    request_id: str,
    response: Response,
    identifier_type: Literal["email", "phone"] = Query(..., alias="match"),
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=4096),
    _admin=Depends(require_roles(settings.admin_role)),
    privacy_repo: PrivacyRequestsRepository = Depends(get_privacy_requests_repo),
    leads_repo: LeadsRepository = Depends(get_leads_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
):
    """Find bounded candidate records only after a company admin verifies identity."""
    privacy_request = privacy_repo.get_by_id(request_id)
    if not privacy_request:
        raise HTTPException(status_code=404, detail="Privacy request not found")
    if privacy_request.status not in {PrivacyRequestStatus.VERIFIED, PrivacyRequestStatus.IN_PROGRESS}:
        raise HTTPException(status_code=409, detail="Verify the request identity before discovering related records")
    source_lead = leads_repo.get_by_id(privacy_request.lead_id)
    if not source_lead:
        raise HTTPException(status_code=404, detail="Privacy request lead not found")
    try:
        matches, next_cursor = leads_repo.find_customer_history_page(
            identifier_type=identifier_type,
            customer_email=source_lead.customer_email,
            customer_phone=source_lead.customer_phone,
            limit=limit,
            cursor=cursor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if next_cursor:
        response.headers["X-Next-Cursor"] = next_cursor
    audit_repo.create(
        AuditEventCreate(
            lead_id=privacy_request.lead_id,
            action="privacy_subject_records_discovered",
            actor=f"user:{_admin['sub']}",
            details={
                "privacy_request_id": privacy_request.request_id,
                "identifier_type": identifier_type,
                "match_count": len(matches),
                "matched_lead_ids": [lead.lead_id for lead in matches],
                "has_more": bool(next_cursor),
            },
        )
    )
    return [
        PrivacyRecordMatch(
            lead_id=lead.lead_id,
            created_at=lead.created_at,
            source=lead.source.value,
            lifecycle_status=lead.lifecycle_status.value,
        )
        for lead in matches
    ]


@router.get("/leads/{lead_id}/export", summary="Export a lead record and its history")
def export_lead_data(
    lead_id: str,
    operator=Depends(require_roles(settings.admin_role)),
    leads_repo: LeadsRepository = Depends(get_leads_repo),
    followups_repo: FollowUpsRepository = Depends(get_followups_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
    whatsapp_repo: WhatsAppMessagesRepository = Depends(get_whatsapp_messages_repo),
):
    """Return one tenant-scoped lead record with all related follow-ups and audit pages."""
    lead = leads_repo.get_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    followups = []
    cursor = None
    while True:
        page, cursor = followups_repo.list_followups_page(limit=100, cursor=cursor, lead_id=lead_id)
        followups.extend(page)
        if cursor is None:
            break

    whatsapp_messages = whatsapp_repo.all_for_lead(lead_id)

    events = []
    cursor = None
    while True:
        page, cursor = audit_repo.list_by_lead_page(lead_id, limit=100, cursor=cursor)
        events.extend(page)
        if cursor is None:
            break

    exported_at = datetime.now(timezone.utc).isoformat()
    export_event = audit_repo.create(
        AuditEventCreate(
            lead_id=lead_id,
            action="lead_data_exported",
            actor=f"user:{operator['sub']}",
            details={"followup_count": len(followups), "audit_event_count": len(events), "whatsapp_message_count": len(whatsapp_messages)},
        )
    )
    payload = {
        "schema_version": "1.0",
        "exported_at": exported_at,
        "tenant_id": settings.effective_tenant_id,
        "lead": lead.model_dump(mode="json"),
        "followups": [item.model_dump(mode="json") for item in followups],
        "audit_events": [item.model_dump(mode="json") for item in [*events, export_event]],
        "whatsapp_messages": [item.model_dump(mode="json") for item in whatsapp_messages],
    }
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", lead_id)[:80] or "record"
    return Response(
        content=json.dumps(payload, ensure_ascii=False),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="lead-{safe_id}-export.json"',
            "Cache-Control": "private, no-store",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )
