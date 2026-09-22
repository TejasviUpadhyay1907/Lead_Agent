"""Company-admin data export for an individual lead record."""

import json
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from app.api.deps import get_audit_repo, get_followups_repo, get_leads_repo
from app.api.security import require_roles
from app.config.settings import settings
from app.models.audit import AuditEventCreate
from app.repositories.audit import AuditRepository
from app.repositories.followups import FollowUpsRepository
from app.repositories.leads import LeadsRepository

router = APIRouter(prefix="/privacy", tags=["Privacy"])


@router.get("/leads/{lead_id}/export", summary="Export a lead record and its history")
def export_lead_data(
    lead_id: str,
    operator=Depends(require_roles(settings.admin_role)),
    leads_repo: LeadsRepository = Depends(get_leads_repo),
    followups_repo: FollowUpsRepository = Depends(get_followups_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
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
            details={"followup_count": len(followups), "audit_event_count": len(events)},
        )
    )
    payload = {
        "schema_version": "1.0",
        "exported_at": exported_at,
        "tenant_id": settings.effective_tenant_id,
        "lead": lead.model_dump(mode="json"),
        "followups": [item.model_dump(mode="json") for item in followups],
        "audit_events": [item.model_dump(mode="json") for item in [*events, export_event]],
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
