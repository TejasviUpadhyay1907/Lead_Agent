"""
LeadRescue AI — Demo Clock & Seeding API Endpoints
Provides API endpoints for advancing demo time (+20m), resetting clock, and seeding synthetic canonical leads.
"""

from datetime import timedelta
from typing import Dict, Optional
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.api.deps import get_audit_repo, get_config_repo, get_leads_repo
from app.models.audit import AuditEventCreate
from app.policy.risk import evaluate_risk
from app.repositories.audit import AuditRepository
from app.repositories.config import ConfigRepository
from app.repositories.leads import LeadsRepository
from app.utils.seed_data import get_canonical_lead_creates
from app.utils.time import effective_now, effective_now_iso, reset_simulated_now, set_simulated_now

router = APIRouter(prefix="/demo", tags=["Demo"])


class AdvanceTimeRequest(BaseModel):
    minutes: int = 20


@router.post("/advance-time")
async def advance_demo_time(
    req: AdvanceTimeRequest,
    leads_repo: LeadsRepository = Depends(get_leads_repo),
    config_repo: ConfigRepository = Depends(get_config_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
):
    """
    Advance simulated demo clock by N minutes (default 20m) and re-evaluate risk across leads.
    """
    new_time = effective_now() + timedelta(minutes=req.minutes)
    set_simulated_now(new_time)

    # Re-evaluate risk across active leads
    business_rules = config_repo.get_config("business_rules").config_value
    all_leads = leads_repo.list_leads()
    at_risk_count = 0

    for lead in all_leads:
        new_risk, _ = evaluate_risk(lead, business_rules)
        if new_risk != lead.risk_status:
            lead.risk_status = new_risk
            leads_repo.save(lead)
            if new_risk.value == "at_risk":
                at_risk_count += 1
                audit_repo.create(
                    AuditEventCreate(
                        lead_id=lead.lead_id,
                        action="risk_changed",
                        actor="demo_clock",
                        details={"new_risk": "at_risk", "advanced_minutes": req.minutes},
                    )
                )

    return {
        "status": "success",
        "advanced_minutes": req.minutes,
        "effective_now": effective_now_iso(),
        "leads_at_risk": at_risk_count,
    }


@router.post("/reset-clock")
async def reset_demo_clock(
    leads_repo: LeadsRepository = Depends(get_leads_repo),
    config_repo: ConfigRepository = Depends(get_config_repo),
):
    """Reset simulated clock back to real system UTC time and re-evaluate risk."""
    reset_simulated_now()
    business_rules = config_repo.get_config("business_rules").config_value
    for lead in leads_repo.list_leads():
        new_risk, _ = evaluate_risk(lead, business_rules)
        if new_risk != lead.risk_status:
            lead.risk_status = new_risk
            leads_repo.save(lead)

    return {"status": "success", "effective_now": effective_now_iso()}


@router.post("/seed")
async def seed_canonical_leads(
    leads_repo: LeadsRepository = Depends(get_leads_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
):
    """Seed the 5 canonical Phase 0 test leads (Rahul, Priya, Amit, Deepak, Sunita)."""
    seed_leads = get_canonical_lead_creates()
    created = []
    for l_in in seed_leads:
        lead = leads_repo.create(l_in)
        created.append(lead)
        audit_repo.create(
            AuditEventCreate(
                lead_id=lead.lead_id,
                action="lead_received",
                actor="system_seed",
                details={"customer_name": lead.customer_name, "source": lead.source.value},
            )
        )

    return {"status": "success", "seeded_count": len(created), "leads": created}
