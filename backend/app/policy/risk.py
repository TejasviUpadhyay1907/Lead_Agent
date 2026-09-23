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

    target_mins = int(response_target_minutes) if response_target_minutes is not None else 20
    at_risk_dt = created_dt + timedelta(minutes=target_mins)
    return at_risk_dt.isoformat()


def evaluate_risk(lead: Lead, business_rules: Dict[str, any]) -> Tuple[RiskStatusEnum, str]:
    """
    Evaluates risk status:
    at_risk_at = created_at + response_target_minutes
    Risk is AT_RISK if effective_now() >= at_risk_at and no provider-confirmed
    response was sent, unless lifecycle is resolved or opted out.
    """
    response_target = business_rules.get("response_target_minutes", 20)
    at_risk_at_iso = calculate_at_risk_timestamp(lead.created_at, response_target)

    # Stop conditions / resolved leads are never at_risk
    if lead.lifecycle_status in [LifecycleStatusEnum.RESOLVED, LifecycleStatusEnum.OPTED_OUT]:
        return RiskStatusEnum.NORMAL, at_risk_at_iso

    # Only a provider-confirmed send satisfies the response SLA. Approval and
    # legacy simulated-send records do not establish that a customer was reached.
    if lead.response_status == ResponseStatusEnum.SENT:
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
