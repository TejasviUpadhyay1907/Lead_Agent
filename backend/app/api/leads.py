"""
LeadRescue AI — Leads API Endpoints
Endpoints for lead creation, listing, detailed retrieval, and AI analysis.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.agent.lead_agent import LeadRescueAgent
from app.api.deps import get_audit_repo, get_leads_repo
from app.models.audit import AuditEventCreate
from app.models.enums import LifecycleStatusEnum, PriorityEnum, ResponseStatusEnum, RiskStatusEnum, SourceEnum
from app.models.lead import Lead, LeadCreate
from app.repositories.audit import AuditRepository
from app.repositories.leads import LeadsRepository

router = APIRouter(prefix="/leads", tags=["Leads"])


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
    audit_repo: AuditRepository = Depends(get_audit_repo),
):
    """
    Invoke Strands Agent to understand and extract details for a lead.
    
    CRITICAL ARCHITECTURE BOUNDARY:
    - AI agent extracts intent, urgency, product, quantity, location, customer stage, key entities, summary, recommendation, and response draft.
    - AI agent DOES NOT score, assign priority (HOT/WARM/COLD), calculate risk, schedule follow-ups, or mutate state.
    """
    lead = leads_repo.get_by_id(lead_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead with ID '{lead_id}' not found",
        )

    # Invoke Strands Agent Runner
    agent_runner = LeadRescueAgent()
    analysis_result, execution_events = agent_runner.analyze_lead(lead_id)

    # Persist ONLY AI Understanding Fields (No score, priority, risk, or follow-ups)
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

    # Update lifecycle status to ANALYZED (unless already opted_out)
    if lead.lifecycle_status != LifecycleStatusEnum.OPTED_OUT:
        lead.lifecycle_status = LifecycleStatusEnum.ANALYZED

    # Save updated lead
    saved_lead = leads_repo.save(lead)

    # Record Audit Event
    audit_repo.create(
        AuditEventCreate(
            lead_id=lead_id,
            action="lead_analyzed",
            actor="agent",
            details={
                "intent": analysis_result.intent.value,
                "urgency": analysis_result.urgency.value,
                "product": analysis_result.product,
                "quantity": analysis_result.quantity,
                "events_count": len(execution_events),
            },
        )
    )

    return saved_lead
