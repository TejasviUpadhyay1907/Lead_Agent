"""
LeadRescue AI — Deterministic Scoring Engine
Calculates lead score (0-100) using deterministic signals independent of LLM reasoning.
"""

from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
from pydantic import BaseModel, ConfigDict, Field

from app.models.agent import AgentAnalysisResult
from app.models.enums import CustomerStageEnum, IntentEnum, UrgencyEnum
from app.models.lead import Lead
from app.utils.time import effective_now


class ScoreResult(BaseModel):
    """Structured, explainable score output."""
    total_score: int = Field(..., ge=0, le=100)
    score_breakdown: Dict[str, int]
    signals: Dict[str, str]
    max_possible_score: int = 100

    model_config = ConfigDict(extra="forbid")


def calculate_recency_points(created_at_iso: str) -> Tuple[int, str]:
    """Calculates recency points based on lead age relative to effective_now()."""
    try:
        dt = datetime.fromisoformat(created_at_iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except Exception:
        return 5, "< 1 hour"

    age_seconds = (effective_now() - dt).total_seconds()
    age_hours = age_seconds / 3600.0

    if age_hours < 1.0:
        return 5, "< 1 hour"
    elif age_hours < 4.0:
        return 2, "< 4 hours"
    else:
        return 0, ">= 4 hours"


def calculate_score(
    lead: Lead,
    analysis: AgentAnalysisResult,
    business_rules: Dict[str, any],
    lead_value: Optional[float] = None,
) -> ScoreResult:
    """
    Deterministically computes lead score (0-100) and breakdown signals.
    """
    score_breakdown: Dict[str, int] = {}
    signals: Dict[str, str] = {}
    total = 0

    # 1. Intent Category (Mutually Exclusive)
    if analysis.intent == IntentEnum.PURCHASE:
        score_breakdown["intent"] = 25
        signals["intent"] = "Purchase Intent (+25)"
    elif analysis.intent == IntentEnum.INQUIRY:
        score_breakdown["intent"] = 12
        signals["intent"] = "Inquiry Intent (+12)"
    else:
        score_breakdown["intent"] = 5
        signals["intent"] = "Support/Other Intent (+5)"
    total += score_breakdown["intent"]

    # 2. Urgency Category (Mutually Exclusive)
    if analysis.urgency == UrgencyEnum.HIGH:
        score_breakdown["urgency"] = 20
        signals["urgency"] = "High Urgency (+20)"
    elif analysis.urgency == UrgencyEnum.MEDIUM:
        score_breakdown["urgency"] = 10
        signals["urgency"] = "Medium Urgency (+10)"
    else:
        score_breakdown["urgency"] = 0
        signals["urgency"] = "Low Urgency (+0)"
    total += score_breakdown["urgency"]

    # 3. Quantity Category (Mutually Exclusive)
    if analysis.quantity is not None and analysis.quantity >= 10:
        score_breakdown["quantity"] = 20
        signals["quantity"] = f"Bulk Quantity {analysis.quantity} >= 10 (+20)"
    elif analysis.quantity is not None and analysis.quantity >= 1:
        score_breakdown["quantity"] = 10
        signals["quantity"] = f"Specified Quantity {analysis.quantity} 1-9 (+10)"
    else:
        score_breakdown["quantity"] = 0
        signals["quantity"] = "Unspecified Quantity (+0)"
    total += score_breakdown["quantity"]

    # 4. Product Specified Category
    if analysis.product and len(analysis.product.strip()) > 0:
        score_breakdown["product"] = 15
        signals["product"] = f"Product Specified '{analysis.product}' (+15)"
    else:
        score_breakdown["product"] = 0
        signals["product"] = "No Product Specified (+0)"
    total += score_breakdown["product"]

    # 5. Location Specified Category
    if analysis.location and len(analysis.location.strip()) > 0:
        score_breakdown["location"] = 5
        signals["location"] = f"Location Specified '{analysis.location}' (+5)"
    else:
        score_breakdown["location"] = 0
        signals["location"] = "No Location Specified (+0)"
    total += score_breakdown["location"]

    # 6. Customer Stage Category
    if analysis.customer_stage == CustomerStageEnum.RETURNING:
        score_breakdown["customer_stage"] = 5
        signals["customer_stage"] = "Returning Customer (+5)"
    else:
        score_breakdown["customer_stage"] = 3
        signals["customer_stage"] = "New Customer (+3)"
    total += score_breakdown["customer_stage"]

    # 7. Recency Category
    recency_pts, recency_label = calculate_recency_points(lead.created_at)
    score_breakdown["recency"] = recency_pts
    signals["recency"] = f"Recency {recency_label} (+{recency_pts})"
    total += score_breakdown["recency"]

    # 8. High-Value Threshold Category
    high_val_thresh = business_rules.get("high_value_threshold", 50000)
    if lead_value is not None and lead_value > high_val_thresh:
        score_breakdown["high_value"] = 5
        signals["high_value"] = f"Value > {high_val_thresh} (+5)"
        total += score_breakdown["high_value"]
    else:
        score_breakdown["high_value"] = 0
        signals["high_value"] = "Below High-Value Threshold (+0)"

    # Clamp total score between 0 and 100
    final_score = max(0, min(100, total))

    return ScoreResult(
        total_score=final_score,
        score_breakdown=score_breakdown,
        signals=signals,
        max_possible_score=100,
    )
