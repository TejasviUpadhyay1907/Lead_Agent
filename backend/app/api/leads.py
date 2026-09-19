"""
LeadRescue AI — Leads API Endpoints
Endpoints for lead creation, listing, detailed retrieval, AI analysis, and response approval.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.agent.lead_agent import LeadRescueAgent
from app.api.deps import get_audit_repo, get_config_repo, get_followups_repo, get_leads_repo
from app.models.audit import AuditEventCreate
from app.models.enums import LifecycleStatusEnum, PriorityEnum, ResponseStatusEnum, RiskStatusEnum, SourceEnum
from app.models.lead import Lead, LeadCreate
from app.policy.engine import PolicyEngine
from app.repositories.audit import AuditRepository
from app.repositories.config import ConfigRepository
from app.repositories.followups import FollowUpsRepository
from app.repositories.leads import LeadsRepository

router = APIRouter(prefix="/leads", tags=["Leads"])


class ResponseActionRequest(BaseModel):
    action: str  # "approve" | "edit" | "reject"
    response_draft: Optional[str] = None


@router.post("", response_model=Lead, status_code=status.HTTP_201_CREATED)
async def create_lead(
    lead_in: LeadCreate,
    leads_repo: LeadsRepository = Depends(get_leads_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
):
    """
    Create a new incoming lead.
    Creates lead record and logs an audit event.
    """
    lead = leads_repo.create(lead_in)

    # Opt-out check on raw message (e.g. Lead 5 Sunita Rao)
    raw_lower = lead_in.raw_message.lower()
    if any(phrase in raw_lower for phrase in ["remove me", "unsubscribe", "stop contact", "opt out", "don't contact"]):
        lead.lifecycle_status = LifecycleStatusEnum.OPTED_OUT
        leads_repo.save(lead)

    # Record Audit event
    audit_repo.create(
        AuditEventCreate(
            lead_id=lead.lead_id,
            action="lead_received",
            actor="system",
            details={
                "customer_name": lead.customer_name,
                "source": lead.source.value,
                "lifecycle_status": lead.lifecycle_status.value,
            },
        )
    )

    return lead


@router.get("", response_model=List[Lead])
async def list_leads(
    lifecycle_status: Optional[LifecycleStatusEnum] = Query(None, description="Filter by lifecycle status"),
    priority: Optional[PriorityEnum] = Query(None, description="Filter by priority"),
    risk_status: Optional[RiskStatusEnum] = Query(None, description="Filter by risk status"),
    source: Optional[SourceEnum] = Query(None, description="Filter by source"),
    leads_repo: LeadsRepository = Depends(get_leads_repo),
):
    """
    List and filter leads.
    """
    return leads_repo.list_leads(
        lifecycle_status=lifecycle_status.value if lifecycle_status else None,
        priority=priority.value if priority else None,
        risk_status=risk_status.value if risk_status else None,
        source=source.value if source else None,
    )


@router.get("/{lead_id}", response_model=Lead)
async def get_lead(
    lead_id: str,
    leads_repo: LeadsRepository = Depends(get_leads_repo),
):
    """
    Get detailed record for a specific lead.
    """
    lead = leads_repo.get_by_id(lead_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead with ID '{lead_id}' not found",
        )
    return lead


@router.post("/{lead_id}/analyze", response_model=Lead)
async def analyze_lead(
    lead_id: str,
    leads_repo: LeadsRepository = Depends(get_leads_repo),
    followups_repo: FollowUpsRepository = Depends(get_followups_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
    config_repo: ConfigRepository = Depends(get_config_repo),
):
    """
    Invoke Strands Agent for understanding + Deterministic Policy Engine for decisions.
    
    ARCHITECTURE SEPARATION:
    1. Strands Agent -> Understands (AgentAnalysisResult).
    2. Policy Engine -> Decides score, priority, risk, lifecycle, and follow-up.
    """
    lead = leads_repo.get_by_id(lead_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead with ID '{lead_id}' not found",
        )

    # Fetch configuration & existing follow-ups
    business_rules = config_repo.get_config("business_rules").config_value
    existing_followups = followups_repo.list_followups(lead_id=lead_id)

    # 1. AI Understanding Layer (Strands Agent)
    agent_runner = LeadRescueAgent()
    analysis_result, execution_events = agent_runner.analyze_lead(lead_id)

    # Update AI Understanding Fields
    lead.intent = analysis_result.intent
    lead.urgency = analysis_result.urgency
    lead.product = analysis_result.product
    lead.quantity = analysis_result.quantity
    lead.location = analysis_result.location
    lead.customer_stage = analysis_result.customer_stage
    lead.key_entities = analysis_result.key_entities
    lead.ai_summary = analysis_result.summary
    lead.recommended_action = analysis_result.recommended_action
    lead.response_draft = analysis_result.response_draft
    lead.response_status = ResponseStatusEnum.DRAFT

    # 2. Deterministic Decision Layer (Policy Engine)
    policy_res = PolicyEngine.evaluate(
        lead=lead,
        analysis=analysis_result,
        business_rules=business_rules,
        existing_followups=existing_followups,
    )

    # Update Deterministic Decision Fields
    if policy_res.score_result:
        lead.score = policy_res.score_result.total_score
        lead.score_breakdown = policy_res.score_result.score_breakdown
    else:
        lead.score = None
        lead.score_breakdown = {}

    lead.priority = policy_res.priority
    lead.lifecycle_status = policy_res.lifecycle_status
    lead.risk_status = policy_res.risk_status
    lead.at_risk_at = policy_res.at_risk_at

    # Create Follow-up if recommended by policy engine
    if policy_res.followup_recommendation:
        followups_repo.create(policy_res.followup_recommendation)

    # Save lead
    saved_lead = leads_repo.save(lead)

    # Record Audit Trail Event
    audit_repo.create(
        AuditEventCreate(
            lead_id=lead_id,
            action="lead_analyzed",
            actor="policy_engine",
            details={
                "intent": analysis_result.intent.value,
                "urgency": analysis_result.urgency.value,
                "score": lead.score,
                "priority": lead.priority.value if lead.priority else None,
                "risk_status": lead.risk_status.value,
                "lifecycle_status": lead.lifecycle_status.value,
                "followup_created": bool(policy_res.followup_recommendation),
                "audit_notes": policy_res.audit_notes,
            },
        )
    )

    return saved_lead


@router.post("/{lead_id}/respond", response_model=Lead)
async def respond_to_lead(
    lead_id: str,
    req: ResponseActionRequest,
    leads_repo: LeadsRepository = Depends(get_leads_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
):
    """
    Human operator action endpoint: Approve & Simulate Send, Edit Draft, or Reject Response.
    """
    lead = leads_repo.get_by_id(lead_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead with ID '{lead_id}' not found",
        )

    if req.response_draft:
        lead.response_draft = req.response_draft

    if req.action == "approve":
        lead.response_status = ResponseStatusEnum.SIMULATED_SENT
        lead.lifecycle_status = LifecycleStatusEnum.CONTACTED
        lead.risk_status = RiskStatusEnum.NORMAL
        action_name = "response_simulated_sent"
        actor = "human_operator"
    elif req.action == "reject":
        lead.response_status = ResponseStatusEnum.REJECTED
        action_name = "response_rejected"
        actor = "human_operator"
    else:  # edit
        lead.response_status = ResponseStatusEnum.DRAFT
        action_name = "response_edited"
        actor = "human_operator"

    saved_lead = leads_repo.save(lead)

    audit_repo.create(
        AuditEventCreate(
            lead_id=lead_id,
            action=action_name,
            actor=actor,
            details={"action": req.action, "response_status": saved_lead.response_status.value},
        )
    )

    return saved_lead
