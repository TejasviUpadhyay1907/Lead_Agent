"""Tenant-scoped operational and outcome reports."""

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_leads_repo
from app.api.security import require_roles
from app.config.settings import settings
from app.repositories.leads import LeadsRepository

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/outcomes")
def get_outcome_report_page(
    start_date: date = Query(..., description="UTC cohort start date, inclusive"),
    end_date: date = Query(..., description="UTC cohort end date, inclusive"),
    cursor: Optional[str] = Query(default=None, max_length=4096),
    _operator=Depends(require_roles(settings.operator_role, settings.admin_role)),
    leads_repo: LeadsRepository = Depends(get_leads_repo),
):
    """Return one page of outcome counts for leads received in the UTC date window."""
    today = datetime.now(timezone.utc).date()
    if start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    if end_date > today:
        raise HTTPException(status_code=422, detail="end_date cannot be in the future")
    if end_date - start_date > timedelta(days=364):
        raise HTTPException(status_code=422, detail="Outcome reports are limited to a 365-day window")

    start_at = datetime.combine(start_date, time.min, tzinfo=timezone.utc).isoformat()
    end_at = datetime.combine(end_date, time.max, tzinfo=timezone.utc).isoformat()
    try:
        page = leads_repo.outcome_report_page(start_at, end_at, cursor=cursor, limit=100)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid report cursor") from exc
    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "cohort": "lead_created_at_utc",
        **page,
    }
