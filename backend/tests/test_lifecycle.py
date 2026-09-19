"""
LeadRescue AI — Lifecycle State Machine Tests
"""

from app.models.enums import LifecycleStatusEnum
from app.policy.lifecycle import can_transition, evaluate_lifecycle_transition


def test_valid_lifecycle_transitions():
    assert can_transition(LifecycleStatusEnum.NEW, LifecycleStatusEnum.ANALYZED)
    assert can_transition(LifecycleStatusEnum.ANALYZED, LifecycleStatusEnum.CONTACTED)
    assert can_transition(LifecycleStatusEnum.ANALYZED, LifecycleStatusEnum.RESOLVED)
    assert can_transition(LifecycleStatusEnum.ANALYZED, LifecycleStatusEnum.OPTED_OUT)


def test_invalid_lifecycle_transition():
    # Cannot jump from NEW to RESOLVED directly without analyzed / opted_out
    assert not can_transition(LifecycleStatusEnum.NEW, LifecycleStatusEnum.RESOLVED)


def test_customer_declined_mapping():
    ok, msg, final_state = evaluate_lifecycle_transition(
        LifecycleStatusEnum.CONTACTED,
        LifecycleStatusEnum.RESOLVED,
        reason="customer_declined",
    )
    assert ok is True
    assert final_state == LifecycleStatusEnum.RESOLVED
    assert "declined" in msg
