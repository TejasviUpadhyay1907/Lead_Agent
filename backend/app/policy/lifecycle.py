"""
LeadRescue AI — Lifecycle State Machine
Enforces valid state transitions and customer decline handling.
"""

from typing import Tuple
from app.models.enums import LifecycleStatusEnum

VALID_TRANSITIONS = {
    LifecycleStatusEnum.NEW: [LifecycleStatusEnum.ANALYZED, LifecycleStatusEnum.OPTED_OUT],
    LifecycleStatusEnum.ANALYZED: [
        LifecycleStatusEnum.CONTACTED,
        LifecycleStatusEnum.FOLLOW_UP,
        LifecycleStatusEnum.RESOLVED,
        LifecycleStatusEnum.OPTED_OUT,
    ],
    LifecycleStatusEnum.CONTACTED: [
        LifecycleStatusEnum.FOLLOW_UP,
        LifecycleStatusEnum.RESOLVED,
        LifecycleStatusEnum.OPTED_OUT,
    ],
    LifecycleStatusEnum.FOLLOW_UP: [LifecycleStatusEnum.RESOLVED, LifecycleStatusEnum.OPTED_OUT],
    LifecycleStatusEnum.RESOLVED: [],  # Terminal state
    LifecycleStatusEnum.OPTED_OUT: [],  # Terminal state
}


def can_transition(current: LifecycleStatusEnum, target: LifecycleStatusEnum) -> bool:
    """Returns True if state transition is allowed."""
    if current == target:
        return True
    allowed = VALID_TRANSITIONS.get(current, [])
    return target in allowed


def evaluate_lifecycle_transition(
    current: LifecycleStatusEnum,
    target: LifecycleStatusEnum,
    reason: str = None,
) -> Tuple[bool, str, LifecycleStatusEnum]:
    """
    Evaluates lifecycle transition:
    Handles 'customer_declined' mapping to LifecycleStatusEnum.RESOLVED.
    """
    # Customer decline mapping rule (Phase 1 decision)
    if reason == "customer_declined":
        return True, "Customer declined outreach -> marked as resolved", LifecycleStatusEnum.RESOLVED

    if can_transition(current, target):
        return True, f"Transition from {current.value} to {target.value} allowed", target
    else:
        return False, f"Invalid state transition from {current.value} to {target.value}", current
