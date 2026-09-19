"""
LeadRescue AI — FollowUps API Endpoints
Endpoint for listing follow-up tasks.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query

from app.api.deps import get_followups_repo
from app.models.enums import FollowUpStatusEnum
from app.models.followup import FollowUp
from app.repositories.followups import FollowUpsRepository

router = APIRouter(prefix="/followups", tags=["FollowUps"])


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
