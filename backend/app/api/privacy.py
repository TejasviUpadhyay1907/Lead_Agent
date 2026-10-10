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
MAX_PRIVACY_BUNDLE_RECORDS = 100
MAX_PRIVACY_BUNDLE_BYTES = 8 * 1024 * 1024


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

    return _export_lead_record(
        lead,
        operator,
        followups_repo,
        audit_repo,
        whatsapp_repo,
        audit_action="lead_data_exported",
        audit_details={},
        filename_prefix="lead",
    )


def _export_lead_record(
    lead,
    operator,
    followups_repo: FollowUpsRepository,
    audit_repo: AuditRepository,
    whatsapp_repo: WhatsAppMessagesRepository,
    *,
    audit_action: str,
    audit_details: dict,
    filename_prefix: str,
    export_context: dict | None = None,
):
    """Build a no-store export for one lead and its complete local history."""
    record = _collect_lead_record(lead, followups_repo, audit_repo, whatsapp_repo)
    exported_at = datetime.now(timezone.utc).isoformat()
    export_event = audit_repo.create(
        AuditEventCreate(
            lead_id=lead.lead_id,
            action=audit_action,
            actor=f"user:{operator['sub']}",
            details={
                **audit_details,
                "followup_count": len(record["followups"]),
                "audit_event_count": len(record["audit_events"]),
                "whatsapp_message_count": len(record["whatsapp_messages"]),
            },
        )
    )
    record["audit_events"].append(export_event.model_dump(mode="json"))
    payload = {
        "schema_version": "1.0",
        "exported_at": exported_at,
        "tenant_id": settings.effective_tenant_id,
        **record,
    }
    if export_context:
        payload["export_context"] = export_context
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", lead.lead_id)[:80] or "record"
    return _json_download(payload, f"{filename_prefix}-{safe_id}-export.json")


def _collect_lead_record(
    lead,
    followups_repo: FollowUpsRepository,
    audit_repo: AuditRepository,
    whatsapp_repo: WhatsAppMessagesRepository,
) -> dict:
    """Collect one lead and all locally stored related records."""
    followups = []
    cursor = None
    while True:
        page, cursor = followups_repo.list_followups_page(limit=100, cursor=cursor, lead_id=lead.lead_id)
        followups.extend(page)
        if cursor is None:
            break

    whatsapp_messages = whatsapp_repo.all_for_lead(lead.lead_id)

    events = []
    cursor = None
    while True:
        page, cursor = audit_repo.list_by_lead_page(lead.lead_id, limit=100, cursor=cursor)
        events.extend(page)
        if cursor is None:
            break
    return {
        "lead": lead.model_dump(mode="json"),
        "followups": [item.model_dump(mode="json") for item in followups],
        "audit_events": [item.model_dump(mode="json") for item in events],
        "whatsapp_messages": [item.model_dump(mode="json") for item in whatsapp_messages],
    }


def _json_download(payload: dict, filename: str) -> Response:
    return Response(
        content=json.dumps(payload, ensure_ascii=False),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/requests/{request_id}/export",
    summary="Export all local records matching one verified access identifier",
)
def export_privacy_request_bundle(
    request_id: str,
    identifier_type: Literal["email", "phone"] = Query(..., alias="match"),
    operator=Depends(require_roles(settings.admin_role)),
    privacy_repo: PrivacyRequestsRepository = Depends(get_privacy_requests_repo),
    leads_repo: LeadsRepository = Depends(get_leads_repo),
    followups_repo: FollowUpsRepository = Depends(get_followups_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
    whatsapp_repo: WhatsAppMessagesRepository = Depends(get_whatsapp_messages_repo),
):
    """Download a bounded bundle of all LeadRescue records for one verified identifier."""
    privacy_request = privacy_repo.get_by_id(request_id)
    if not privacy_request:
        raise HTTPException(status_code=404, detail="Privacy request not found")
    if privacy_request.request_type.value != "access":
        raise HTTPException(status_code=409, detail="Data bundles are only available for access requests")
    if privacy_request.status not in {PrivacyRequestStatus.VERIFIED, PrivacyRequestStatus.IN_PROGRESS}:
        raise HTTPException(status_code=409, detail="Verify the request identity before exporting matching records")

    source_lead = leads_repo.get_by_id(privacy_request.lead_id)
    if not source_lead:
        raise HTTPException(status_code=404, detail="Privacy request lead not found")
    identifier = source_lead.customer_email if identifier_type == "email" else source_lead.customer_phone
    if not identifier or not identifier.strip():
        raise HTTPException(status_code=422, detail=f"The request record has no stored {identifier_type} to match")

    try:
        leads, next_cursor = leads_repo.find_customer_history_page(
            identifier_type=identifier_type,
            customer_email=source_lead.customer_email,
            customer_phone=source_lead.customer_phone,
            limit=MAX_PRIVACY_BUNDLE_RECORDS,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="The verified contact identifier could not be matched") from exc
    if next_cursor:
        raise HTTPException(
            status_code=413,
            detail=f"More than {MAX_PRIVACY_BUNDLE_RECORDS} records match this identifier. Use the paged record list and export individual records.",
        )
    if all(lead.lead_id != source_lead.lead_id for lead in leads):
        if len(leads) >= MAX_PRIVACY_BUNDLE_RECORDS:
            raise HTTPException(status_code=413, detail="The matching record limit was reached. Use individual record exports.")
        leads.append(source_lead)
        leads.sort(key=lambda lead: (lead.created_at, lead.lead_id), reverse=True)

    records = []
    current_size = 0
    related_counts = {"followups": 0, "audit_events": 0, "whatsapp_messages": 0}
    for lead in leads:
        record = _collect_lead_record(lead, followups_repo, audit_repo, whatsapp_repo)
        current_size += len(json.dumps(record, ensure_ascii=False).encode("utf-8"))
        if current_size > MAX_PRIVACY_BUNDLE_BYTES:
            raise HTTPException(
                status_code=413,
                detail="The matching data exceeds the export size limit. Use the paged record list and export individual records.",
            )
        related_counts["followups"] += len(record["followups"])
        related_counts["audit_events"] += len(record["audit_events"])
        related_counts["whatsapp_messages"] += len(record["whatsapp_messages"])
        records.append(record)

    exported_at = datetime.now(timezone.utc).isoformat()
    export_event = audit_repo.build(AuditEventCreate(
        lead_id=source_lead.lead_id,
        action="privacy_subject_bundle_exported",
        actor=f"user:{operator['sub']}",
        details={
            "privacy_request_id": privacy_request.request_id,
            "identifier_type": identifier_type,
            "matched_record_count": len(records),
            "matched_lead_ids": [record["lead"]["lead_id"] for record in records],
            **related_counts,
        },
    ))
    payload = {
        "schema_version": "1.1",
        "exported_at": exported_at,
        "tenant_id": settings.effective_tenant_id,
        "records": records,
        "export_context": {
            "privacy_request_id": privacy_request.request_id,
            "identifier_type": identifier_type,
            "scope": f"all_indexed_local_records_matching_verified_{identifier_type}",
            "complete_for_selected_identifier": False,
            "complete_for_current_index_results": True,
            "index_consistency": "eventually_consistent",
            "complete_subject_export": False,
            "limitations": [
                "This bundle includes records matching one verified email or phone only.",
                "Customer-history GSIs are eventually consistent; verify index backfills and wait for recent changes before treating this as complete.",
                "It does not discover changed or alternate identifiers or records in Zoho, Meta, or other external systems.",
                "Confirm the corresponding email and phone match lists and use the approved process for external systems before completing the request.",
            ],
        },
    }
    for record in records:
        if record["lead"]["lead_id"] == source_lead.lead_id:
            record["audit_events"].append(export_event.model_dump(mode="json"))
            break
    body = json.dumps(payload, ensure_ascii=False)
    if len(body.encode("utf-8")) > MAX_PRIVACY_BUNDLE_BYTES:
        raise HTTPException(status_code=413, detail="The export exceeds the response size limit. Use individual record exports.")
    audit_repo.store(export_event)
    safe_request_id = re.sub(r"[^A-Za-z0-9_-]", "_", privacy_request.request_id)[:48]
    return _json_download(payload, f"access-{safe_request_id}-{identifier_type}-bundle.json")


@router.get(
    "/requests/{request_id}/records/{lead_id}/export",
    summary="Export one lead matched to a verified access request",
)
def export_privacy_request_record(
    request_id: str,
    lead_id: str,
    identifier_type: Literal["email", "phone"] = Query(..., alias="match"),
    operator=Depends(require_roles(settings.admin_role)),
    privacy_repo: PrivacyRequestsRepository = Depends(get_privacy_requests_repo),
    leads_repo: LeadsRepository = Depends(get_leads_repo),
    followups_repo: FollowUpsRepository = Depends(get_followups_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
    whatsapp_repo: WhatsAppMessagesRepository = Depends(get_whatsapp_messages_repo),
):
    """Export a single matching record only after access-request identity verification."""
    privacy_request = privacy_repo.get_by_id(request_id)
    if not privacy_request:
        raise HTTPException(status_code=404, detail="Privacy request not found")
    if privacy_request.request_type.value != "access":
        raise HTTPException(status_code=409, detail="Record exports are only available for access requests")
    if privacy_request.status not in {PrivacyRequestStatus.VERIFIED, PrivacyRequestStatus.IN_PROGRESS}:
        raise HTTPException(status_code=409, detail="Verify the request identity before exporting records")

    source_lead = leads_repo.get_by_id(privacy_request.lead_id)
    lead = leads_repo.get_by_id(lead_id)
    if not source_lead or not lead:
        raise HTTPException(status_code=404, detail="Matching lead record not found")
    if identifier_type == "email":
        source_identifier = (source_lead.customer_email or "").strip().casefold()
        candidate_identifier = (lead.customer_email or "").strip().casefold()
    else:
        source_identifier = re.sub(r"\D", "", source_lead.customer_phone or "")
        candidate_identifier = re.sub(r"\D", "", lead.customer_phone or "")
    if not source_identifier or source_identifier != candidate_identifier:
        raise HTTPException(status_code=404, detail="Matching lead record not found")

    return _export_lead_record(
        lead,
        operator,
        followups_repo,
        audit_repo,
        whatsapp_repo,
        audit_action="privacy_subject_record_exported",
        audit_details={
            "privacy_request_id": privacy_request.request_id,
            "identifier_type": identifier_type,
        },
        filename_prefix=f"access-{request_id[:12]}",
        export_context={
            "privacy_request_id": privacy_request.request_id,
            "identifier_type": identifier_type,
            "scope": "one_lead_record_and_its_local_history",
            "complete_subject_export": False,
            "limitation": "This export covers one LeadRescue lead matched by the selected stored identifier. It does not include other identifiers or external systems.",
        },
    )
