"""
LeadRescue AI — Policy Engine Orchestration
Combines scoring, priority classification, risk evaluation, lifecycle state,
and follow-up recommendations deterministically.

CENTRAL ARCHITECTURAL RULE:
- The AI understands.
- The software decides.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.agent import AgentAnalysisResult
from app.models.enums import LifecycleStatusEnum, PriorityEnum, RiskStatusEnum
from app.models.followup import FollowUp, FollowUpCreate
from app.models.lead import Lead
from app.policy.followups import create_followup_recommendation
from app.policy.guardrails import check_opt_out
from app.policy.lifecycle import evaluate_lifecycle_transition
from app.policy.priority import classify_priority
from app.policy.risk import evaluate_risk
from app.policy.scoring import ScoreResult, calculate_score


class PolicyEvaluationResult(BaseModel):
    """Complete output of deterministic policy evaluation."""
    score_result: Optional[ScoreResult] = None
    priority: PriorityEnum
    lifecycle_status: LifecycleStatusEnum
    risk_status: RiskStatusEnum
    at_risk_at: Optional[str] = None
    followup_recommendation: Optional[FollowUpCreate] = None
    opt_out_detected: bool = False
    audit_notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class PolicyEngine:
    """
    Deterministic policy engine for LeadRescue AI.
    Executes business rules independently of LLM reasoning.
    """

    @staticmethod
    def evaluate(
        lead: Lead,
        analysis: AgentAnalysisResult,
        business_rules: Dict[str, Any],
        existing_followups: Optional[List[FollowUp]] = None,
        lead_value: Optional[float] = None,
    ) -> PolicyEvaluationResult:
        if existing_followups is None:
            existing_followups = []

        notes = []

        # 1. Deterministic Opt-Out Guardrail Check
        is_opt_out, opt_reason = check_opt_out(lead.raw_message)
        if is_opt_out or lead.lifecycle_status == LifecycleStatusEnum.OPTED_OUT:
            notes.append(f"Opt-out enforced: {opt_reason}")
            return PolicyEvaluationResult(
                score_result=None,
                priority=PriorityEnum.COLD,
                lifecycle_status=LifecycleStatusEnum.OPTED_OUT,
                risk_status=RiskStatusEnum.NORMAL,
                at_risk_at=None,
                followup_recommendation=None,
                opt_out_detected=True,
                audit_notes=notes,
            )

        # 2. Score Calculation
        score_res = calculate_score(lead, analysis, business_rules, lead_value=lead_value)
        notes.append(f"Calculated score: {score_res.total_score}/100")

        # 3. Priority Classification
        priority = classify_priority(score_res.total_score)
        notes.append(f"Assigned priority: {priority.value}")

        # 4. Risk Evaluation
        risk_status, at_risk_at_iso = evaluate_risk(lead, business_rules)
        notes.append(f"Evaluated risk: {risk_status.value} (At risk at: {at_risk_at_iso})")

        # 5. Lifecycle Transition Evaluation
        target_lifecycle = LifecycleStatusEnum.ANALYZED
        can_trans, trans_msg, final_lifecycle = evaluate_lifecycle_transition(lead.lifecycle_status, target_lifecycle)
        notes.append(trans_msg)

        # 6. Follow-up Recommendation Engine
        followup_rec = create_followup_recommendation(lead, priority, existing_followups)
        if followup_rec:
            notes.append(f"Follow-up scheduled for due_at: {followup_rec.due_at}")
        else:
            notes.append("No follow-up scheduled")

        return PolicyEvaluationResult(
            score_result=score_res,
            priority=priority,
            lifecycle_status=final_lifecycle,
            risk_status=risk_status,
            at_risk_at=at_risk_at_iso,
            followup_recommendation=followup_rec,
            opt_out_detected=False,
            audit_notes=notes,
        )
