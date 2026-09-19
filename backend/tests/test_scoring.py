"""
LeadRescue AI — Scoring Engine Unit Tests (LLM Independent)
Directly tests calculate_score without LLM, Strands, Bedrock, or AWS dependencies.
"""

from app.models.agent import AgentAnalysisResult
from app.models.enums import CustomerStageEnum, IntentEnum, UrgencyEnum
from app.models.lead import Lead
from app.policy.scoring import calculate_score


def test_scoring_purchase_high_urgency_bulk():
    lead = Lead(customer_name="Test Customer", raw_message="Test message")
    analysis = AgentAnalysisResult(
        intent=IntentEnum.PURCHASE,
        urgency=UrgencyEnum.HIGH,
        product="CNC machines",
        quantity=10,
        location="Pune",
        customer_stage=CustomerStageEnum.NEW,
        summary="Summary text",
        recommended_action="Action text",
        response_draft="Draft text",
    )
    business_rules = {"high_value_threshold": 50000}

    # Signals: Purchase (25) + High (20) + Qty>=10 (20) + Product (15) + Location (5) + New (3) + Recency<1h (5) = 93
    res = calculate_score(lead, analysis, business_rules)
    assert res.total_score == 93
    assert res.score_breakdown["intent"] == 25
    assert res.score_breakdown["urgency"] == 20
    assert res.score_breakdown["quantity"] == 20
    assert res.score_breakdown["product"] == 15
    assert res.score_breakdown["location"] == 5
    assert res.score_breakdown["customer_stage"] == 3
    assert res.score_breakdown["recency"] == 5


def test_scoring_inquiry_low_urgency():
    lead = Lead(customer_name="Test Customer", raw_message="Test message")
    analysis = AgentAnalysisResult(
        intent=IntentEnum.INQUIRY,
        urgency=UrgencyEnum.LOW,
        product="Solar Panels",
        customer_stage=CustomerStageEnum.NEW,
        summary="Summary text",
        recommended_action="Action text",
        response_draft="Draft text",
    )
    business_rules = {"high_value_threshold": 50000}

    # Signals: Inquiry (12) + Low (0) + Qty(0) + Product (15) + Location(0) + New (3) + Recency<1h (5) = 35
    res = calculate_score(lead, analysis, business_rules)
    assert res.total_score == 35


def test_scoring_quantity_mutually_exclusive():
    """Quantity >= 10 receives +20, NOT +20+10."""
    lead = Lead(customer_name="Test Customer", raw_message="Test message")
    analysis = AgentAnalysisResult(
        intent=IntentEnum.PURCHASE,
        urgency=UrgencyEnum.LOW,
        quantity=15,
        summary="Summary",
        recommended_action="Action",
        response_draft="Draft",
    )
    res = calculate_score(lead, analysis, {})
    assert res.score_breakdown["quantity"] == 20  # +20 only, not +30!


def test_scoring_returning_customer_and_high_value():
    lead = Lead(customer_name="Test Customer", raw_message="Test message")
    analysis = AgentAnalysisResult(
        intent=IntentEnum.PURCHASE,
        urgency=UrgencyEnum.MEDIUM,
        customer_stage=CustomerStageEnum.RETURNING,
        summary="Summary",
        recommended_action="Action",
        response_draft="Draft",
    )
    res = calculate_score(lead, analysis, {"high_value_threshold": 50000}, lead_value=60000)
    assert res.score_breakdown["customer_stage"] == 5
    assert res.score_breakdown["high_value"] == 5


def test_scoring_bounds_clamping():
    """Score must never exceed 100 or drop below 0."""
    lead = Lead(customer_name="Test Customer", raw_message="Test message")
    analysis = AgentAnalysisResult(
        intent=IntentEnum.PURCHASE,
        urgency=UrgencyEnum.HIGH,
        product="Heavy Machinery",
        quantity=50,
        location="Delhi",
        customer_stage=CustomerStageEnum.RETURNING,
        summary="Summary",
        recommended_action="Action",
        response_draft="Draft",
    )
    res = calculate_score(lead, analysis, {"high_value_threshold": 50000}, lead_value=100000)
    # Sum: 25+20+20+15+5+5+5+5 = 100
    assert res.total_score <= 100
    assert res.total_score >= 0
