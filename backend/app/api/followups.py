"""
LeadRescue AI — FollowUps API Endpoints
Endpoints for listing and updating follow-up tasks.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import get_audit_repo, get_followups_repo
from app.models.audit import AuditEventCreate
from app.models.enums import FollowUpStatusEnum
from app.models.followup import FollowUp
from app.repositories.audit import AuditRepository
from app.repositories.followups import FollowUpsRepository
from app.utils.time import effective_now_iso

router = APIRouter(prefix="/followups", tags=["FollowUps"])


class UpdateFollowupRequest(BaseModel):
    status: FollowUpStatusEnum = Field(..., description="Target status: completed | cancelled | blocked")
    notes: Optional[str] = Field(None, description="Optional completion/cancellation notes")


@router.get("", response_model=List[FollowUp])
async def list_followups(
    lead_id: Optional[str] = Query(None, description="Filter by lead ID"),
    status: Optional[FollowUpStatusEnum] = Query(None, description="Filter by follow-up status"),
    followups_repo: FollowUpsRepository = Depends(get_followups_repo),
):
    """
    List follow-up tasks with optional filters.
    """
    return followups_repo.list_followups(
        lead_id=lead_id,
        status=status.value if status else None,
    )


@router.put("/{followup_id}", response_model=FollowUp)
async def update_followup(
    followup_id: str,
    req: UpdateFollowupRequest,
    followups_repo: FollowUpsRepository = Depends(get_followups_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
):
    """
    Update follow-up task status (complete, cancel, block).
    """
    followup = followups_repo.get_by_id(followup_id)
    if not followup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Follow-up task with ID '{followup_id}' not found",
        )

    prev_status = followup.status
    followup.status = req.status
    if req.notes:
        followup.notes = req.notes

    if req.status == FollowUpStatusEnum.COMPLETED:
        followup.completed_at = effective_now_iso()
        action_name = "followup_completed"
    elif req.status == FollowUpStatusEnum.CANCELLED:
        action_name = "followup_cancelled"
    else:
        action_name = "followup_blocked"

    saved = followups_repo.save(followup)

    audit_repo.create(
        AuditEventCreate(
            lead_id=followup.lead_id,
            action=action_name,
            actor="human_operator",
            details={
                "followup_id": followup_id,
                "previous_status": prev_status.value,
                "new_status": req.status.value,
                "notes": req.notes,
            },
        )
    )

    return saved
