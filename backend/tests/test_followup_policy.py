"""
LeadRescue AI — Follow-Up Engine Unit Tests
"""

from app.models.enums import LifecycleStatusEnum, PriorityEnum
from app.models.followup import FollowUp
from app.models.lead import Lead
from app.policy.followups import calculate_followup_due_at, create_followup_recommendation, should_schedule_followup


def test_followup_scheduling_for_normal_lead():
    lead = Lead(customer_name="Rahul", raw_message="Need CNC machines")
    rec = create_followup_recommendation(lead, PriorityEnum.HOT, [])
    assert rec is not None
    assert rec.lead_id == lead.lead_id
    assert "HOT Priority" in rec.action


def test_followup_blocked_for_opted_out_or_resolved():
    opted_lead = Lead(customer_name="Sunita", raw_message="Remove me", lifecycle_status=LifecycleStatusEnum.OPTED_OUT)
    ok, reason = should_schedule_followup(opted_lead, PriorityEnum.COLD, [])
    assert ok is False
    assert "Stop Condition" in reason

    resolved_lead = Lead(customer_name="Resolved", raw_message="Done", lifecycle_status=LifecycleStatusEnum.RESOLVED)
    ok, reason = should_schedule_followup(resolved_lead, PriorityEnum.WARM, [])
    assert ok is False


def test_max_followup_limit():
    lead = Lead(customer_name="Test", raw_message="Inquiry")
    existing = [
        FollowUp(lead_id=lead.lead_id, action="F1", due_at="2026-09-19T10:00:00Z"),
        FollowUp(lead_id=lead.lead_id, action="F2", due_at="2026-09-19T11:00:00Z"),
        FollowUp(lead_id=lead.lead_id, action="F3", due_at="2026-09-19T12:00:00Z"),
    ]
    ok, reason = should_schedule_followup(lead, PriorityEnum.HOT, existing)
    assert ok is False
    assert "limit" in reason
