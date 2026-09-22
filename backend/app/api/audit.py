"""
LeadRescue AI — Audit API Endpoints
Endpoint for retrieving audit history of a specific lead.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.deps import get_audit_repo, get_leads_repo
from app.api.security import require_roles
from app.config.settings import settings
from app.models.audit import AuditEvent
from app.repositories.audit import AuditRepository
from app.repositories.leads import LeadsRepository

router = APIRouter(tags=["Audit"])


@router.get("/leads/{lead_id}/audit", response_model=List[AuditEvent])
def get_lead_audit(
    response: Response,
    lead_id: str,
    _operator=Depends(require_roles(settings.operator_role, settings.admin_role)),
    limit: int = Query(50, ge=1, le=100),
    cursor: Optional[str] = Query(None, max_length=4096),
    leads_repo: LeadsRepository = Depends(get_leads_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
):
    """
    Get full audit trail for a lead.
    """
    lead = leads_repo.get_by_id(lead_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead with ID '{lead_id}' not found",
        )
    try:
        events, next_cursor = audit_repo.list_by_lead_page(lead_id, limit=limit, cursor=cursor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if next_cursor:
        response.headers["X-Next-Cursor"] = next_cursor
    return events
