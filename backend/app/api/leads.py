"""
LeadRescue AI — Leads API Endpoints
Endpoints for lead creation, listing, detailed retrieval, AI analysis, response approval, rescue, and status updates.
"""

from typing import List, Optional
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.agent.lead_agent import LeadRescueAgent
from app.api.deps import get_audit_repo, get_config_repo, get_followups_repo, get_leads_repo
from app.models.audit import AuditEventCreate
from app.models.enums import FollowUpStatusEnum, LifecycleStatusEnum, PriorityEnum, ResponseStatusEnum, RiskStatusEnum, SourceEnum
from app.models.followup import FollowUpCreate
from app.models.lead import Lead, LeadCreate
from app.policy.engine import PolicyEngine
from app.policy.risk import evaluate_risk
from app.repositories.audit import AuditRepository
from app.repositories.config import ConfigRepository
from app.repositories.followups import FollowUpsRepository
from app.repositories.leads import LeadsRepository
from app.utils.time import effective_now

router = APIRouter(prefix="/leads", tags=["Leads"])


class ResponseActionRequest(BaseModel):
    action: str = Field(..., description="Action type: approve | edit | reject")
    edited_draft: Optional[str] = Field(None, description="Edited draft text when action is 'edit' or 'approve'")
    response_draft: Optional[str] = Field(None, description="Alias for edited_draft for backwards compatibility")


class UpdateStatusRequest(BaseModel):
    lifecycle_status: LifecycleStatusEnum
    reason: Optional[str] = None


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
    config_repo: ConfigRepository = Depends(get_config_repo),
):
    """
    List and filter leads with real-time risk re-evaluation against effective_now().
    """
    business_rules = config_repo.get_config("business_rules").config_value
    leads = leads_repo.list_leads()
    
    # Re-evaluate risk dynamically against current effective time
    for lead in leads:
        new_risk, _ = evaluate_risk(lead, business_rules)
        if new_risk != lead.risk_status:
            lead.risk_status = new_risk
            leads_repo.save(lead)

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
    config_repo: ConfigRepository = Depends(get_config_repo),
):
    """
    Get detailed record for a specific lead with dynamic risk re-evaluation.
    """
    lead = leads_repo.get_by_id(lead_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead with ID '{lead_id}' not found",
        )
    
    # Re-evaluate risk against effective_now()
    business_rules = config_repo.get_config("business_rules").config_value
    new_risk, _ = evaluate_risk(lead, business_rules)
    if new_risk != lead.risk_status:
        lead.risk_status = new_risk
        lead = leads_repo.save(lead)

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


async def process_response_action(
    lead_id: str,
    req: ResponseActionRequest,
    leads_repo: LeadsRepository,
    audit_repo: AuditRepository,
) -> Lead:
    """Core logic for human operator response actions (approve, edit, reject)."""
    lead = leads_repo.get_by_id(lead_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead with ID '{lead_id}' not found",
        )

    # Guardrail 1: Opt-Out Check
    if lead.lifecycle_status == LifecycleStatusEnum.OPTED_OUT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Response not allowed: customer has opted out.",
        )

    # Guardrail 2: Resolved Check
    if lead.lifecycle_status == LifecycleStatusEnum.RESOLVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Response not allowed: lead is already resolved.",
        )

    draft_text = req.edited_draft or req.response_draft
    if draft_text:
        lead.response_draft = draft_text

    if req.action == "approve":
        if not lead.response_draft or not lead.response_draft.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid response draft available for approval.",
            )
        lead.response_status = ResponseStatusEnum.SIMULATED_SENT
        # Update lifecycle to contacted when operator approves response
        if lead.lifecycle_status in [LifecycleStatusEnum.NEW, LifecycleStatusEnum.ANALYZED, LifecycleStatusEnum.FOLLOW_UP]:
            lead.lifecycle_status = LifecycleStatusEnum.CONTACTED
        # Suppress SLA risk upon response approval
        lead.risk_status = RiskStatusEnum.NORMAL
        
        saved_lead = leads_repo.save(lead)

        audit_repo.create(
            AuditEventCreate(
                lead_id=lead_id,
                action="response_approved",
                actor="human_operator",
                details={"action": "approve"},
            )
        )
        audit_repo.create(
            AuditEventCreate(
                lead_id=lead_id,
                action="response_simulated_sent",
                actor="human_operator",
                details={"simulated": True, "notice": "No external message sent"},
            )
        )
        return saved_lead

    elif req.action == "edit":
        if not draft_text or not draft_text.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Edited draft text cannot be empty.",
            )
        lead.response_status = ResponseStatusEnum.DRAFT
        saved_lead = leads_repo.save(lead)

        audit_repo.create(
            AuditEventCreate(
                lead_id=lead_id,
                action="response_edited",
                actor="human_operator",
                details={"action": "edit"},
            )
        )
        return saved_lead

    elif req.action == "reject":
        lead.response_status = ResponseStatusEnum.REJECTED
        saved_lead = leads_repo.save(lead)

        audit_repo.create(
            AuditEventCreate(
                lead_id=lead_id,
                action="response_rejected",
                actor="human_operator",
                details={"action": "reject"},
            )
        )
        return saved_lead

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid action '{req.action}'. Supported actions: approve, edit, reject.",
        )


@router.put("/{lead_id}/response", response_model=Lead)
async def update_lead_response(
    lead_id: str,
    req: ResponseActionRequest,
    leads_repo: LeadsRepository = Depends(get_leads_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
):
    """
    Canonical Human Response Workflow Endpoint: Approve & Simulate Send, Edit, or Reject.
    """
    return await process_response_action(lead_id, req, leads_repo, audit_repo)


@router.post("/{lead_id}/respond", response_model=Lead)
async def respond_to_lead_alias(
    lead_id: str,
    req: ResponseActionRequest,
    leads_repo: LeadsRepository = Depends(get_leads_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
):
    """
    Backwards-compatible alias for response approval workflow.
    """
    return await process_response_action(lead_id, req, leads_repo, audit_repo)


@router.post("/{lead_id}/rescue")
async def rescue_lead(
    lead_id: str,
    leads_repo: LeadsRepository = Depends(get_leads_repo),
    followups_repo: FollowUpsRepository = Depends(get_followups_repo),
    config_repo: ConfigRepository = Depends(get_config_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
):
    """
    100% Deterministic Lead Rescue Endpoint.
    Evaluates policy eligibility without LLM inference.
    """
    lead = leads_repo.get_by_id(lead_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead with ID '{lead_id}' not found",
        )

    # 1. Opt-out guardrail check
    if lead.lifecycle_status == LifecycleStatusEnum.OPTED_OUT:
        audit_repo.create(
            AuditEventCreate(
                lead_id=lead_id,
                action="rescue_blocked",
                actor="policy_engine",
                details={"reason": "customer_opted_out"},
            )
        )
        return {"rescued": False, "reason": "customer_opted_out"}

    # 2. Resolved guardrail check
    if lead.lifecycle_status == LifecycleStatusEnum.RESOLVED:
        audit_repo.create(
            AuditEventCreate(
                lead_id=lead_id,
                action="rescue_blocked",
                actor="policy_engine",
                details={"reason": "lead_already_resolved"},
            )
        )
        return {"rescued": False, "reason": "lead_already_resolved"}

    # 3. Dynamic Risk Evaluation against effective_now()
    business_rules = config_repo.get_config("business_rules").config_value
    current_risk, _ = evaluate_risk(lead, business_rules)
    lead.risk_status = current_risk

    if current_risk != RiskStatusEnum.AT_RISK:
        audit_repo.create(
            AuditEventCreate(
                lead_id=lead_id,
                action="rescue_blocked",
                actor="policy_engine",
                details={"reason": "lead_not_at_risk"},
            )
        )
        return {"rescued": False, "reason": "lead_not_at_risk"}

    # 4. Check active follow-ups limit & existing scheduled rescue
    existing_followups = followups_repo.list_followups(lead_id=lead_id)
    active_followups = [f for f in existing_followups if f.status in [FollowUpStatusEnum.SCHEDULED, FollowUpStatusEnum.OVERDUE]]
    
    if len(active_followups) >= 3:
        audit_repo.create(
            AuditEventCreate(
                lead_id=lead_id,
                action="rescue_blocked",
                actor="policy_engine",
                details={"reason": "max_active_followups_reached"},
            )
        )
        return {"rescued": False, "reason": "max_active_followups_reached"}

    # 5. Deterministic Policy Follow-up Interval
    now = effective_now()
    p = (lead.priority.value if lead.priority else "cold").lower()
    if p == "hot":
        due_dt = now + timedelta(minutes=30)
    elif p == "warm":
        due_dt = now + timedelta(hours=2)
    else:
        due_dt = now + timedelta(hours=24)

    due_at_str = due_dt.isoformat()

    # Create Priority Rescue Follow-Up
    new_followup = followups_repo.create(
        FollowUpCreate(
            lead_id=lead_id,
            action=f"Priority Rescue Action ({p.upper()})",
            due_at=due_at_str,
            status=FollowUpStatusEnum.SCHEDULED,
            notes="Deterministic rescue triggered due to SLA breach.",
        )
    )

    # Update lifecycle status to follow_up if not resolved
    if lead.lifecycle_status != LifecycleStatusEnum.RESOLVED:
        lead.lifecycle_status = LifecycleStatusEnum.FOLLOW_UP
        leads_repo.save(lead)

    audit_repo.create(
        AuditEventCreate(
            lead_id=lead_id,
            action="rescue_triggered",
            actor="policy_engine",
            details={
                "followup_id": new_followup.followup_id,
                "priority": p.upper(),
                "due_at": due_at_str,
            },
        )
    )

    return {
        "rescued": True,
        "reason": "sla_breached",
        "action": "priority_follow_up",
        "followup_id": new_followup.followup_id,
        "due_at": due_at_str,
    }


@router.put("/{lead_id}/status", response_model=Lead)
async def update_lead_status(
    lead_id: str,
    req: UpdateStatusRequest,
    leads_repo: LeadsRepository = Depends(get_leads_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
):
    """
    Update lead lifecycle status (e.g. resolve lead upon customer decline).
    """
    lead = leads_repo.get_by_id(lead_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead with ID '{lead_id}' not found",
        )

    prev_status = lead.lifecycle_status
    target_status = req.lifecycle_status

    if req.reason == "customer_declined":
        target_status = LifecycleStatusEnum.RESOLVED

    lead.lifecycle_status = target_status
    saved_lead = leads_repo.save(lead)

    audit_repo.create(
        AuditEventCreate(
            lead_id=lead_id,
            action="lifecycle_changed",
            actor="human_operator",
            details={
                "previous_status": prev_status.value,
                "new_status": target_status.value,
                "reason": req.reason,
            },
        )
    )

    return saved_lead
