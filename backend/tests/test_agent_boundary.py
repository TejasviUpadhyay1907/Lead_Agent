"""
LeadRescue AI — AI vs Deterministic Boundary Contract Tests
Verifies that AgentAnalysisResult strictly rejects unauthorized deterministic fields.
"""

import pytest
from pydantic import ValidationError

from app.models.agent import AgentAnalysisResult
from app.models.enums import CustomerStageEnum, IntentEnum, UrgencyEnum


def test_valid_agent_analysis_result():
    """Valid agent extraction containing ONLY allowed understanding/drafting fields."""
    result = AgentAnalysisResult(
        intent=IntentEnum.PURCHASE,
        urgency=UrgencyEnum.HIGH,
        product="CNC machines",
        quantity=10,
        location="Pune",
        customer_stage=CustomerStageEnum.NEW,
        key_entities=["CNC machines", "Pune", "urgent delivery"],
        summary="Customer requesting 10 CNC machines with urgent delivery to Pune.",
        recommended_action="Contact immediately with specs and pricing.",
        response_draft="Hi Rahul! Thanks for reaching out about the CNC machines...",
    )
    assert result.intent == IntentEnum.PURCHASE
    assert result.quantity == 10


def test_agent_contract_rejects_score():
    """Agent is FORBIDDEN from producing a lead score."""
    with pytest.raises(ValidationError) as exc:
        AgentAnalysisResult(
            intent=IntentEnum.PURCHASE,
            urgency=UrgencyEnum.HIGH,
            summary="Summary text",
            recommended_action="Action text",
            response_draft="Draft text",
            score=93,  # FORBIDDEN!
        )
    assert "extra_forbidden" in str(exc.value) or "score" in str(exc.value)


def test_agent_contract_rejects_priority():
    """Agent is FORBIDDEN from assigning HOT / WARM / COLD priority."""
    with pytest.raises(ValidationError) as exc:
        AgentAnalysisResult(
            intent=IntentEnum.PURCHASE,
            urgency=UrgencyEnum.HIGH,
            summary="Summary text",
            recommended_action="Action text",
            response_draft="Draft text",
            priority="HOT",  # FORBIDDEN!
        )
    assert "extra_forbidden" in str(exc.value) or "priority" in str(exc.value)


def test_agent_contract_rejects_risk_status():
    """Agent is FORBIDDEN from setting risk status."""
    with pytest.raises(ValidationError):
        AgentAnalysisResult(
            intent=IntentEnum.PURCHASE,
            urgency=UrgencyEnum.HIGH,
            summary="Summary text",
            recommended_action="Action text",
            response_draft="Draft text",
            risk_status="at_risk",  # FORBIDDEN!
        )


def test_agent_contract_rejects_database_mutations():
    """Agent is FORBIDDEN from outputting mutation directives."""
    with pytest.raises(ValidationError):
        AgentAnalysisResult(
            intent=IntentEnum.PURCHASE,
            urgency=UrgencyEnum.HIGH,
            summary="Summary text",
            recommended_action="Action text",
            response_draft="Draft text",
            lifecycle_status="contacted",  # FORBIDDEN!
            create_followup=True,          # FORBIDDEN!
            send_action="whatsapp",        # FORBIDDEN!
        )
