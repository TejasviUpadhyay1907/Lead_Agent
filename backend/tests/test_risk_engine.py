"""
LeadRescue AI — Risk Engine Unit Tests
Tests at-risk calculations against effective_now() demo clock.
"""

from datetime import datetime, timedelta, timezone
from app.models.enums import LifecycleStatusEnum, ResponseStatusEnum, RiskStatusEnum
from app.models.lead import Lead
from app.policy.risk import evaluate_risk
from app.utils.time import reset_simulated_now, set_simulated_now


def test_risk_before_and_after_at_risk_at():
    # Lead created at T0
    t0 = datetime(2026, 9, 19, 10, 0, 0, tzinfo=timezone.utc)
    set_simulated_now(t0)

    lead = Lead(customer_name="Test Lead", raw_message="Test message", created_at=t0.isoformat())
    rules = {"response_target_minutes": 20}

    # At T0 + 10m -> NORMAL
    t_10m = t0 + timedelta(minutes=10)
    set_simulated_now(t_10m)
    status, _ = evaluate_risk(lead, rules)
    assert status == RiskStatusEnum.NORMAL

    # At T0 + 25m -> AT_RISK
    t_25m = t0 + timedelta(minutes=25)
    set_simulated_now(t_25m)
    status, _ = evaluate_risk(lead, rules)
    assert status == RiskStatusEnum.AT_RISK

    reset_simulated_now()


def test_only_confirmed_send_or_resolved_suppresses_at_risk():
    t0 = datetime(2026, 9, 19, 10, 0, 0, tzinfo=timezone.utc)
    t_30m = t0 + timedelta(minutes=30)
    set_simulated_now(t_30m)

    # A provider-confirmed send satisfies the response target.
    sent_lead = Lead(
        customer_name="Sent Lead",
        raw_message="Test",
        created_at=t0.isoformat(),
        response_status=ResponseStatusEnum.SENT,
    )
    status, _ = evaluate_risk(sent_lead, {"response_target_minutes": 20})
    assert status == RiskStatusEnum.NORMAL

    # Approval and legacy simulated sends do not prove that the customer was reached.
    for response_status in (ResponseStatusEnum.APPROVED, ResponseStatusEnum.SIMULATED_SENT):
        unconfirmed_lead = Lead(
            customer_name="Unconfirmed Lead",
            raw_message="Test",
            created_at=t0.isoformat(),
            response_status=response_status,
        )
        status, _ = evaluate_risk(unconfirmed_lead, {"response_target_minutes": 20})
        assert status == RiskStatusEnum.AT_RISK

    # Resolved lead
    resolved_lead = Lead(
        customer_name="Resolved Lead",
        raw_message="Test",
        created_at=t0.isoformat(),
        lifecycle_status=LifecycleStatusEnum.RESOLVED,
    )
    status, _ = evaluate_risk(resolved_lead, {"response_target_minutes": 20})
    assert status == RiskStatusEnum.NORMAL

    reset_simulated_now()
