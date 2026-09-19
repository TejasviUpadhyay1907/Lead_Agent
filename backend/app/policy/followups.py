"""
LeadRescue AI — Deterministic Follow-Up Engine
Schedules follow-ups based on priority, lifecycle state, and stop conditions.
"""

from datetime import timedelta
from typing import Dict, List, Optional, Tuple
from app.models.enums import FollowUpStatusEnum, LifecycleStatusEnum, PriorityEnum
from app.models.followup import FollowUp, FollowUpCreate
from app.models.lead import Lead
from app.utils.time import effective_now, effective_now_iso

MAX_FOLLOWUPS_PER_LEAD = 3


def calculate_followup_due_at(priority: PriorityEnum) -> str:
    """Calculates due timestamp based on priority level."""
    now = effective_now()
    if priority == PriorityEnum.HOT:
        due = now + timedelta(minutes=30)
    elif priority == PriorityEnum.WARM:
        due = now + timedelta(hours=2)
    else:
        due = now + timedelta(hours=24)
    return due.isoformat()


def should_schedule_followup(
    lead: Lead,
    priority: PriorityEnum,
    existing_followups: List[FollowUp],
) -> Tuple[bool, str]:
    """
    Evaluates whether a follow-up should be scheduled.
    """
    # 1. Stop condition check
    if lead.lifecycle_status in [LifecycleStatusEnum.OPTED_OUT, LifecycleStatusEnum.RESOLVED]:
        return False, f"Lead lifecycle is '{lead.lifecycle_status.value}' (Stop Condition)"

    # 2. Maximum follow-up limit
    active_count = len([f for f in existing_followups if f.status in [FollowUpStatusEnum.SCHEDULED, FollowUpStatusEnum.OVERDUE]])
    if active_count >= MAX_FOLLOWUPS_PER_LEAD:
        return False, f"Maximum active follow-up limit ({MAX_FOLLOWUPS_PER_LEAD}) reached"

    return True, "Follow-up scheduling approved"


def create_followup_recommendation(
    lead: Lead,
    priority: PriorityEnum,
    existing_followups: List[FollowUp],
) -> Optional[FollowUpCreate]:
    """
    Creates follow-up recommendation if allowed by policy engine.
    """
    can_schedule, reason = should_schedule_followup(lead, priority, existing_followups)
    if not can_schedule:
        return None

    due_at_iso = calculate_followup_due_at(priority)
    action_text = f"Follow up with {lead.customer_name} ({priority.value} Priority)"

    return FollowUpCreate(
        lead_id=lead.lead_id,
        action=action_text,
        due_at=due_at_iso,
        notes=f"Auto-scheduled by Policy Engine based on {priority.value} priority.",
    )
