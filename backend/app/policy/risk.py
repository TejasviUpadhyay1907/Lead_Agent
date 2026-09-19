"""
LeadRescue AI — Risk Engine
Evaluates at-risk status based on response target SLA and effective clock time.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

from app.models.enums import LifecycleStatusEnum, ResponseStatusEnum, RiskStatusEnum
from app.models.lead import Lead
from app.utils.time import effective_now


def calculate_at_risk_timestamp(created_at_iso: str, response_target_minutes: int) -> str:
    """Calculates ISO timestamp when lead will become at-risk if unresponded."""
    try:
        created_dt = datetime.fromisoformat(created_at_iso.replace("Z", "+00:00"))
        if created_dt.tzinfo is None:
            created_dt = created_dt.replace(tzinfo=timezone.utc)
    except Exception:
        created_dt = effective_now()

    at_risk_dt = created_dt + timedelta(minutes=response_target_minutes)
    return at_risk_dt.isoformat()


def evaluate_risk(lead: Lead, business_rules: Dict[str, any]) -> Tuple[RiskStatusEnum, str]:
    """
    Evaluates risk status:
    at_risk_at = created_at + response_target_minutes
    Risk is AT_RISK if effective_now() >= at_risk_at AND response_status != simulated_sent AND lifecycle not in (resolved, opted_out).
    """
    response_target = business_rules.get("response_target_minutes", 20)
    at_risk_at_iso = calculate_at_risk_timestamp(lead.created_at, response_target)

    # Stop conditions / resolved leads are never at_risk
    if lead.lifecycle_status in [LifecycleStatusEnum.RESOLVED, LifecycleStatusEnum.OPTED_OUT]:
        return RiskStatusEnum.NORMAL, at_risk_at_iso

    # Sent responses are safe
    if lead.response_status == ResponseStatusEnum.SIMULATED_SENT:
        return RiskStatusEnum.NORMAL, at_risk_at_iso

    # Parse at_risk_at dt
    try:
        at_risk_dt = datetime.fromisoformat(at_risk_at_iso.replace("Z", "+00:00"))
        if at_risk_dt.tzinfo is None:
            at_risk_dt = at_risk_dt.replace(tzinfo=timezone.utc)
    except Exception:
        return RiskStatusEnum.NORMAL, at_risk_at_iso

    # Compare against effective_now()
    if effective_now() >= at_risk_dt:
        return RiskStatusEnum.AT_RISK, at_risk_at_iso

    return RiskStatusEnum.NORMAL, at_risk_at_iso
