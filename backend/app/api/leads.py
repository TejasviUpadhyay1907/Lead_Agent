"""
LeadRescue AI — Leads API Endpoints
Endpoints for lead creation, listing, detailed retrieval, AI analysis, response approval, rescue, and status updates.
"""

import json
import re
from decimal import Decimal
from typing import List, Optional
from datetime import timedelta
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
import boto3
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.agent.lead_agent import LeadRescueAgent
from app.api.deps import get_audit_repo, get_config_repo, get_followups_repo, get_leads_repo, get_privacy_requests_repo
from app.api.security import require_roles
from app.config.settings import settings
from app.models.audit import AuditEventCreate
from app.models.enums import FollowUpStatusEnum, LifecycleStatusEnum, PriorityEnum, ResponseStatusEnum, RiskStatusEnum, SalesOutcomeEnum, SourceEnum
from app.models.followup import FollowUp, FollowUpCreate
from app.models.lead import Lead, LeadCreate
from app.models.privacy_request import PrivacyRequest
from app.policy.engine import PolicyEngine
from app.policy.risk import evaluate_risk
from app.repositories.audit import AuditRepository
from app.repositories.config import ConfigRepository
from app.repositories.followups import FollowUpsRepository
from app.repositories.leads import ConcurrentLeadUpdateError, LeadsRepository
from app.repositories.privacy_requests import PrivacyRequestsRepository
from app.repositories.analysis_jobs import repository as analysis_jobs_repo
from app.utils.time import effective_now
from app.policy.guardrails import check_opt_out, detect_privacy_request

router = APIRouter(prefix="/leads", tags=["Leads"])


class ResponseActionRequest(BaseModel):
    action: str = Field(..., description="Action type: approve | edit | reject")
    edited_draft: Optional[str] = Field(None, description="Edited draft text when action is 'edit' or 'approve'")
    response_draft: Optional[str] = Field(None, description="Alias for edited_draft for backwards compatibility")


class UpdateStatusRequest(BaseModel):
    lifecycle_status: LifecycleStatusEnum
    reason: Optional[str] = None


class SalesOutcomeRequest(BaseModel):
    outcome: SalesOutcomeEnum
    sales_value: Optional[Decimal] = Field(default=None, ge=0, le=1_000_000_000_000_000, max_digits=19, decimal_places=4)
    sales_currency: Optional[str] = Field(default=None, pattern=r"^[A-Z]{3}$")
    reason: Optional[str] = Field(default=None, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value):
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def validate_outcome_details(self):
        if self.outcome in {SalesOutcomeEnum.LOST, SalesOutcomeEnum.DISQUALIFIED} and not self.reason:
            raise ValueError("A reason is required for lost or disqualified outcomes")
        if (self.sales_value is None) != (self.sales_currency is None):
            raise ValueError("Sales value and currency must be provided together")
        if self.sales_value is not None and self.outcome != SalesOutcomeEnum.WON:
            raise ValueError("Sales value can only be recorded for a won outcome")
        return self


class AnalysisJobResponse(BaseModel):
    job_id: str
    lead_id: str
    status: str
    created_at: str
    updated_at: str
    error_code: Optional[str] = None
    result: Optional[Lead] = None


@router.post("", response_model=Lead, status_code=status.HTTP_201_CREATED)
def create_lead(
    lead_in: LeadCreate,
    _operator=Depends(require_roles(settings.operator_role, settings.admin_role)),
    leads_repo: LeadsRepository = Depends(get_leads_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
    privacy_repo: PrivacyRequestsRepository = Depends(get_privacy_requests_repo),
):
    """
    Create a new incoming lead.
    Creates lead record and logs an audit event.
    """
    lead = Lead(**lead_in.model_dump())
    privacy_request = detect_privacy_request(lead_in.raw_message)
    privacy_record = PrivacyRequest(
        lead_id=lead.lead_id,
        request_type=privacy_request,
        source="manual",
    ) if privacy_request else None
    lead.privacy_hold = bool(privacy_request)
    opted_out_in_message, _ = check_opt_out(lead_in.raw_message)
    if opted_out_in_message or privacy_request == "erasure" or leads_repo.customer_opted_out(lead):
        lead.lifecycle_status = LifecycleStatusEnum.OPTED_OUT

    audit = audit_repo.build(
        AuditEventCreate(
            lead_id=lead.lead_id,
            action="lead_received",
            actor=f"user:{_operator['sub']}",
            details={
                "source": lead.source.value,
                "lifecycle_status": lead.lifecycle_status.value,
                **({
                    "privacy_request_type": privacy_request,
                    "privacy_request_status": "pending_admin_review",
                    "privacy_request_id": privacy_record.request_id,
                    "admin_action_required": True,
                } if privacy_request else {}),
            },
        )
    )
    lead = leads_repo.create_with_audit(lead, audit, audit_repo, privacy_record, privacy_repo)

    return lead


@router.get("", response_model=List[Lead])
def list_leads(
    response: Response,
    _operator=Depends(require_roles(settings.operator_role, settings.admin_role)),
    lifecycle_status: Optional[LifecycleStatusEnum] = Query(None, description="Filter by lifecycle status"),
    priority: Optional[PriorityEnum] = Query(None, description="Filter by priority"),
    risk_status: Optional[RiskStatusEnum] = Query(None, description="Filter by risk status"),
    source: Optional[SourceEnum] = Query(None, description="Filter by source"),
    limit: int = Query(50, ge=1, le=100),
    cursor: Optional[str] = Query(None, max_length=4096),
    leads_repo: LeadsRepository = Depends(get_leads_repo),
    config_repo: ConfigRepository = Depends(get_config_repo),
):
    """
    List and filter leads with real-time risk re-evaluation against effective_now().
    """
    business_rules = config_repo.get_config("business_rules").config_value
    try:
        leads, next_cursor = leads_repo.list_leads_page(
            limit=limit,
            cursor=cursor,
            lifecycle_status=lifecycle_status.value if lifecycle_status else None,
            priority=priority.value if priority else None,
            source=source.value if source else None,
            risk_status=risk_status.value if risk_status else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if next_cursor:
        response.headers["X-Next-Cursor"] = next_cursor

    # Copy memory repository results before applying response-only projections.
    leads = [lead.model_copy(deep=True) for lead in leads]

    # Batch suppression lookups to avoid two strongly consistent reads per lead.
    opted_out_lead_ids = leads_repo.customer_opted_out_many(leads)

    # Re-evaluate risk dynamically against current effective time
    for lead in leads:
        if lead.lead_id in opted_out_lead_ids:
            lead.lifecycle_status = LifecycleStatusEnum.OPTED_OUT
        new_risk, _ = evaluate_risk(lead, business_rules)
        if new_risk != lead.risk_status:
            lead.risk_status = new_risk

    if risk_status:
        leads = [lead for lead in leads if lead.risk_status == risk_status]
    if lifecycle_status:
        leads = [lead for lead in leads if lead.lifecycle_status == lifecycle_status]
    return leads


@router.get("/{lead_id}", response_model=Lead)
def get_lead(
    lead_id: str,
    _operator=Depends(require_roles(settings.operator_role, settings.admin_role)),
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
    # Memory repository results are shared references; keep GET projections read-only.
    lead = lead.model_copy(deep=True)
    if leads_repo.customer_opted_out(lead):
        lead.lifecycle_status = LifecycleStatusEnum.OPTED_OUT
    # Re-evaluate risk against effective_now()
    business_rules = config_repo.get_config("business_rules").config_value
    new_risk, _ = evaluate_risk(lead, business_rules)
    if new_risk != lead.risk_status:
        lead.risk_status = new_risk

    return lead


def analyze_lead_core(
    lead_id: str,
    _operator,
    leads_repo: LeadsRepository,
    followups_repo: FollowUpsRepository,
    audit_repo: AuditRepository,
    config_repo: ConfigRepository,
    analysis_job_id: Optional[str] = None,
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
    if lead.privacy_hold:
        raise HTTPException(status_code=409, detail="Lead processing is paused while a privacy request is reviewed")
    if analysis_job_id and lead.last_analysis_job_id == analysis_job_id:
        return lead
    if leads_repo.customer_opted_out(lead):
        raise HTTPException(status_code=409, detail="Customer has opted out for this contact")
    expected_updated_at = lead.updated_at

    # Fetch configuration & existing follow-ups
    business_rules = config_repo.get_config("business_rules").config_value
    existing_followups = followups_repo.list_followups(lead_id=lead_id)

    # 1. AI Understanding Layer (Strands Agent)
    agent_runner = LeadRescueAgent()
    try:
        analysis_result, execution_events = agent_runner.analyze_lead(lead_id)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lead analysis is temporarily unavailable",
        ) from exc

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
    if analysis_job_id:
        lead.last_analysis_job_id = analysis_job_id

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

    followups_to_create = (
        [FollowUp(**policy_res.followup_recommendation.model_dump())]
        if policy_res.followup_recommendation else []
    )
    audit = audit_repo.build(
        AuditEventCreate(
            lead_id=lead_id,
            action="lead_analyzed",
            actor=f"user:{_operator['sub']}",
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

    try:
        saved_lead = leads_repo.save_workflow(
            lead, followups_to_create, [audit], followups_repo, audit_repo, expected_updated_at
        )
    except ConcurrentLeadUpdateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This lead changed while analysis was running. Refresh it before analyzing again.",
        ) from exc

    return saved_lead


@router.post("/{lead_id}/analyze", response_model=Lead)
def analyze_lead(
    lead_id: str,
    _operator=Depends(require_roles(settings.operator_role, settings.admin_role)),
    leads_repo: LeadsRepository = Depends(get_leads_repo),
    followups_repo: FollowUpsRepository = Depends(get_followups_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
    config_repo: ConfigRepository = Depends(get_config_repo),
):
    return analyze_lead_core(lead_id, _operator, leads_repo, followups_repo, audit_repo, config_repo)


@router.post("/{lead_id}/analysis-jobs", response_model=AnalysisJobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_analysis_job(
    lead_id: str,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=16, max_length=128),
    _operator=Depends(require_roles(settings.operator_role, settings.admin_role)),
    leads_repo: LeadsRepository = Depends(get_leads_repo),
    followups_repo: FollowUpsRepository = Depends(get_followups_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
    config_repo: ConfigRepository = Depends(get_config_repo),
):
    """Queue durable background analysis and return a pollable job resource."""
    if not re.fullmatch(r"[A-Za-z0-9._:-]{16,128}", idempotency_key):
        raise HTTPException(status_code=400, detail="Invalid idempotency key")
    lead = leads_repo.get_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead with ID '{lead_id}' not found")
    if lead.privacy_hold:
        raise HTTPException(status_code=409, detail="Lead processing is paused while a privacy request is reviewed")
    if leads_repo.customer_opted_out(lead):
        raise HTTPException(status_code=409, detail="Customer has opted out for this contact")
    if not settings.analysis_queue_url:
        if settings.demo_enabled:
            lead = analyze_lead(
                lead_id,
                _operator,
                leads_repo,
                followups_repo,
                audit_repo,
                config_repo,
            )
            now = lead.updated_at
            return AnalysisJobResponse(job_id="demo-completed", lead_id=lead_id, status="SUCCEEDED", created_at=now, updated_at=now, result=lead)
        raise HTTPException(status_code=503, detail="Analysis queue is not configured")

    try:
        job, created = analysis_jobs_repo.create(lead_id, _operator["sub"], idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not created and job.get("status") == "FAILED" and job.get("error_code") == "submission_failed":
        analysis_jobs_repo.set_status(job["job_id"], "QUEUED")
        job["status"] = "QUEUED"
    try:
        if created:
            audit_repo.create(
                AuditEventCreate(
                    lead_id=lead_id,
                    action="analysis_job_requested",
                    actor=f"user:{_operator['sub']}",
                    details={"job_id": job["job_id"]},
                )
            )
        if created or job.get("status") in {"QUEUED", "RETRYING"}:
            boto3.client("sqs", region_name=settings.aws_region or None).send_message(
                QueueUrl=settings.analysis_queue_url,
                MessageBody=json.dumps({"job_id": job["job_id"], "lead_id": lead_id, "actor_id": _operator["sub"]}),
            )
    except Exception as exc:
        analysis_jobs_repo.set_status(job["job_id"], "FAILED", "submission_failed")
        raise HTTPException(status_code=503, detail="Analysis could not be queued") from exc
    return AnalysisJobResponse(**job)


@router.get("/analysis-jobs/{job_id}", response_model=AnalysisJobResponse)
def get_analysis_job(
    job_id: str,
    _operator=Depends(require_roles(settings.operator_role, settings.admin_role)),
):
    job = analysis_jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analysis job not found")
    return AnalysisJobResponse(**job)


def process_response_action(
    lead_id: str,
    req: ResponseActionRequest,
    leads_repo: LeadsRepository,
    audit_repo: AuditRepository,
    config_repo: ConfigRepository,
    actor_id: str,
) -> Lead:
    """Core logic for human operator response actions (approve, edit, reject)."""
    lead = leads_repo.get_by_id(lead_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead with ID '{lead_id}' not found",
        )
    if req.action not in {"approve", "edit", "reject"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid action '{req.action}'. Supported actions: approve, edit, reject.",
        )
    if lead.privacy_hold:
        raise HTTPException(status_code=409, detail="Response actions are paused while a privacy request is reviewed")
    expected_updated_at = lead.updated_at

    def commit_action(*audit_events: AuditEventCreate) -> Lead:
        built_events = [audit_repo.build(event) for event in audit_events]
        try:
            return leads_repo.save_with_audits(lead, built_events, audit_repo, expected_updated_at)
        except ConcurrentLeadUpdateError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This lead was updated by another operator. Refresh it before trying again.",
            ) from exc

    # Guardrail 1: Opt-Out Check
    if lead.lifecycle_status == LifecycleStatusEnum.OPTED_OUT or leads_repo.customer_opted_out(lead):
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

    if lead.response_status == ResponseStatusEnum.SENT and req.action != "approve":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A provider-confirmed sent response cannot be edited or rejected.",
        )

    draft_text = req.edited_draft or req.response_draft
    if req.action == "approve":
        candidate_draft = draft_text if draft_text is not None else lead.response_draft
        if not candidate_draft or not candidate_draft.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid response draft available for approval.",
            )
        if lead.response_status == ResponseStatusEnum.SENT:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This response has already been sent and cannot be approved again.",
            )
        if lead.response_status == ResponseStatusEnum.APPROVED:
            if candidate_draft != lead.response_draft:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Edit the approved draft before approving a changed version.",
                )
            business_rules = config_repo.get_config("business_rules").config_value
            lead.risk_status, lead.at_risk_at = evaluate_risk(lead, business_rules)
            return lead
    elif req.action == "edit" and (not draft_text or not draft_text.strip()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Edited draft text cannot be empty.",
        )
    if draft_text:
        lead.response_draft = draft_text

    if req.action == "approve":
        # Approval records human authorization only. There is no delivery
        # provider configured, so lifecycle and SLA risk remain unchanged.
        lead.response_status = ResponseStatusEnum.APPROVED
        business_rules = config_repo.get_config("business_rules").config_value
        lead.risk_status, lead.at_risk_at = evaluate_risk(lead, business_rules)
        return commit_action(
            AuditEventCreate(
                lead_id=lead_id,
                action="response_approved",
                actor=f"user:{actor_id}",
                details={"action": "approve", "delivery_status": "not_configured"},
            ),
        )

    elif req.action == "edit":
        lead.response_status = ResponseStatusEnum.DRAFT
        return commit_action(
            AuditEventCreate(
                lead_id=lead_id,
                action="response_edited",
                actor=f"user:{actor_id}",
                details={"action": "edit"},
            )
        )

    elif req.action == "reject":
        lead.response_status = ResponseStatusEnum.REJECTED
        return commit_action(
            AuditEventCreate(
                lead_id=lead_id,
                action="response_rejected",
                actor=f"user:{actor_id}",
                details={"action": "reject"},
            )
        )

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid response action")


@router.put("/{lead_id}/response", response_model=Lead)
def update_lead_response(
    lead_id: str,
    req: ResponseActionRequest,
    _operator=Depends(require_roles(settings.operator_role, settings.admin_role)),
    leads_repo: LeadsRepository = Depends(get_leads_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
    config_repo: ConfigRepository = Depends(get_config_repo),
):
    """
    Human response workflow endpoint: approve a draft, edit it, or reject it.
    """
    return process_response_action(lead_id, req, leads_repo, audit_repo, config_repo, _operator["sub"])


@router.post("/{lead_id}/respond", response_model=Lead)
def respond_to_lead_alias(
    lead_id: str,
    req: ResponseActionRequest,
    _operator=Depends(require_roles(settings.operator_role, settings.admin_role)),
    leads_repo: LeadsRepository = Depends(get_leads_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
    config_repo: ConfigRepository = Depends(get_config_repo),
):
    """
    Backwards-compatible alias for response approval workflow.
    """
    return process_response_action(lead_id, req, leads_repo, audit_repo, config_repo, _operator["sub"])


@router.post("/{lead_id}/rescue")
def rescue_lead(
    lead_id: str,
    _operator=Depends(require_roles(settings.operator_role, settings.admin_role)),
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
    if lead.privacy_hold:
        audit_repo.create(
            AuditEventCreate(
                lead_id=lead_id,
                action="rescue_blocked",
                actor=f"user:{_operator['sub']}",
                details={"reason": "privacy_request_pending"},
            )
        )
        return {"rescued": False, "reason": "privacy_request_pending"}
    if leads_repo.customer_opted_out(lead):
        lead.lifecycle_status = LifecycleStatusEnum.OPTED_OUT
    expected_updated_at = lead.updated_at

    # 1. Opt-out guardrail check
    if lead.lifecycle_status == LifecycleStatusEnum.OPTED_OUT:
        audit_repo.create(
            AuditEventCreate(
                lead_id=lead_id,
                action="rescue_blocked",
                actor=f"user:{_operator['sub']}",
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
                actor=f"user:{_operator['sub']}",
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
                actor=f"user:{_operator['sub']}",
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
                actor=f"user:{_operator['sub']}",
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
    new_followup = FollowUp(
        **FollowUpCreate(
            lead_id=lead_id,
            action=f"Priority Rescue Action ({p.upper()})",
            due_at=due_at_str,
            status=FollowUpStatusEnum.SCHEDULED,
            notes="Deterministic rescue triggered due to SLA breach.",
        ).model_dump()
    )

    # Update lifecycle status to follow_up if not resolved
    if lead.lifecycle_status != LifecycleStatusEnum.RESOLVED:
        lead.lifecycle_status = LifecycleStatusEnum.FOLLOW_UP
    audit = audit_repo.build(
        AuditEventCreate(
            lead_id=lead_id,
            action="rescue_triggered",
            actor=f"user:{_operator['sub']}",
            details={
                "followup_id": new_followup.followup_id,
                "priority": p.upper(),
                "due_at": due_at_str,
            },
        )
    )
    try:
        leads_repo.save_with_followup_and_audit(
            lead, new_followup, audit, followups_repo, audit_repo, expected_updated_at
        )
    except ConcurrentLeadUpdateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This lead changed while the rescue was being prepared. Refresh it before retrying.",
        ) from exc

    return {
        "rescued": True,
        "reason": "sla_breached",
        "action": "priority_follow_up",
        "followup_id": new_followup.followup_id,
        "due_at": due_at_str,
    }


@router.put("/{lead_id}/status", response_model=Lead)
def update_lead_status(
    lead_id: str,
    req: UpdateStatusRequest,
    _operator=Depends(require_roles(settings.operator_role, settings.admin_role)),
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
    expected_updated_at = lead.updated_at

    prev_status = lead.lifecycle_status
    target_status = req.lifecycle_status

    if prev_status == LifecycleStatusEnum.OPTED_OUT and target_status != LifecycleStatusEnum.OPTED_OUT:
        raise HTTPException(status_code=400, detail="Customer opt-out is a terminal safeguard and cannot be cleared")
    if req.reason == "customer_declined" and target_status != LifecycleStatusEnum.OPTED_OUT:
        target_status = LifecycleStatusEnum.RESOLVED
    if leads_repo.customer_opted_out(lead):
        target_status = LifecycleStatusEnum.OPTED_OUT

    lead.lifecycle_status = target_status
    audit = audit_repo.build(
        AuditEventCreate(
            lead_id=lead_id,
            action="lifecycle_changed",
            actor=f"user:{_operator['sub']}",
            details={
                "previous_status": prev_status.value,
                "new_status": target_status.value,
                "reason": req.reason,
            },
        )
    )
    try:
        return leads_repo.save_with_audits(lead, [audit], audit_repo, expected_updated_at)
    except ConcurrentLeadUpdateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This lead was updated by another operator. Refresh it before changing its status.",
        ) from exc


@router.put("/{lead_id}/outcome", response_model=Lead)
def update_lead_outcome(
    lead_id: str,
    req: SalesOutcomeRequest,
    _operator=Depends(require_roles(settings.operator_role, settings.admin_role)),
    leads_repo: LeadsRepository = Depends(get_leads_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
):
    """Record an operator-confirmed sales outcome; never treat approval as a conversion."""
    lead = leads_repo.get_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead with ID '{lead_id}' not found")
    if lead.privacy_hold:
        raise HTTPException(status_code=409, detail="Sales outcome changes are paused while a privacy request is reviewed")
    if lead.lifecycle_status == LifecycleStatusEnum.OPTED_OUT or leads_repo.customer_opted_out(lead):
        raise HTTPException(status_code=409, detail="Sales outcome changes are unavailable for a suppressed contact")

    expected_updated_at = lead.updated_at
    previous = {
        "outcome": lead.sales_outcome.value if lead.sales_outcome else None,
        "sales_value": str(lead.sales_value) if lead.sales_value is not None else None,
        "sales_currency": lead.sales_currency,
        "reason": lead.sales_outcome_reason,
    }
    lead.sales_outcome = req.outcome
    lead.sales_value = req.sales_value
    lead.sales_currency = req.sales_currency
    lead.sales_outcome_reason = req.reason
    lead.sales_outcome_at = effective_now().isoformat()
    previous_status = lead.lifecycle_status
    lead.lifecycle_status = LifecycleStatusEnum.RESOLVED
    audit = audit_repo.build(AuditEventCreate(
        lead_id=lead_id,
        action="sales_outcome_recorded",
        actor=f"user:{_operator['sub']}",
        details={
            "previous": previous,
            "outcome": req.outcome.value,
            "sales_value": str(req.sales_value) if req.sales_value is not None else None,
            "sales_currency": req.sales_currency,
            "reason": req.reason,
            "previous_lifecycle_status": previous_status.value,
            "lifecycle_status": LifecycleStatusEnum.RESOLVED.value,
            "source": "operator_entered",
        },
    ))
    try:
        return leads_repo.save_with_audits(lead, [audit], audit_repo, expected_updated_at)
    except ConcurrentLeadUpdateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This lead was updated by another operator. Refresh it before recording its outcome.",
        ) from exc
