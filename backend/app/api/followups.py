"""
LeadRescue AI — FollowUps API Endpoints
Endpoints for listing and updating follow-up tasks.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from app.api.deps import get_audit_repo, get_followups_repo
from app.api.security import require_roles
from app.config.settings import settings
from app.models.audit import AuditEventCreate
from app.models.enums import FollowUpStatusEnum
from app.models.followup import FollowUp
from app.repositories.audit import AuditRepository
from app.repositories.followups import ConcurrentFollowupUpdateError, FollowUpsRepository
from app.utils.time import effective_now_iso

router = APIRouter(prefix="/followups", tags=["FollowUps"])


class UpdateFollowupRequest(BaseModel):
    status: FollowUpStatusEnum = Field(..., description="Target status: completed | cancelled | blocked")
    notes: Optional[str] = Field(None, description="Optional completion/cancellation notes")


@router.get("", response_model=List[FollowUp])
def list_followups(
    response: Response,
    _operator=Depends(require_roles(settings.operator_role, settings.admin_role)),
    lead_id: Optional[str] = Query(None, description="Filter by lead ID"),
    status: Optional[FollowUpStatusEnum] = Query(None, description="Filter by follow-up status"),
    limit: int = Query(50, ge=1, le=100),
    cursor: Optional[str] = Query(None, max_length=4096),
    followups_repo: FollowUpsRepository = Depends(get_followups_repo),
):
    """
    List follow-up tasks with optional filters.
    """
    try:
        items, next_cursor = followups_repo.list_followups_page(
            limit=limit,
            cursor=cursor,
            lead_id=lead_id,
            status=status.value if status else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if next_cursor:
        response.headers["X-Next-Cursor"] = next_cursor
    return items


@router.put("/{followup_id}", response_model=FollowUp)
def update_followup(
    followup_id: str,
    req: UpdateFollowupRequest,
    _operator=Depends(require_roles(settings.operator_role, settings.admin_role)),
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
    expected_status = followup.status
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

    audit = audit_repo.build(
        AuditEventCreate(
            lead_id=followup.lead_id,
            action=action_name,
            actor=f"user:{_operator['sub']}",
            details={
                "followup_id": followup_id,
                "previous_status": prev_status.value,
                "new_status": req.status.value,
            },
        )
    )

    try:
        return followups_repo.save_with_audit(followup, audit, audit_repo, expected_status)
    except ConcurrentFollowupUpdateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This follow-up was updated by another operator. Refresh it before trying again.",
        ) from exc
