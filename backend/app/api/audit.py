"""
LeadRescue AI — Audit API Endpoints
Endpoint for retrieving audit history of a specific lead.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_audit_repo, get_leads_repo
from app.models.audit import AuditEvent
from app.repositories.audit import AuditRepository
from app.repositories.leads import LeadsRepository

router = APIRouter(tags=["Audit"])


@router.get("/leads/{lead_id}/audit", response_model=List[AuditEvent])
async def get_lead_audit(
    lead_id: str,
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
    return audit_repo.list_by_lead(lead_id)
