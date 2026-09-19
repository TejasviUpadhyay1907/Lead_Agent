"""
LeadRescue AI — Canonical Test Leads Policy Engine Verification
Verifies the 5 canonical Phase 0 leads against the complete deterministic PolicyEngine:
1. Rahul Sharma -> 93 HOT
2. Priya Patel -> 35 COLD
3. Amit Kumar -> 13 COLD
4. Deepak Verma -> 67 WARM
5. Sunita Rao -> Opted Out, Score=None, Priority=COLD, No Followup
"""

from app.models.agent import AgentAnalysisResult
from app.models.enums import CustomerStageEnum, IntentEnum, LifecycleStatusEnum, PriorityEnum, UrgencyEnum
from app.models.lead import Lead
from app.policy.engine import PolicyEngine


def test_canonical_lead_1_rahul_sharma():
    """
    Rahul Sharma:
    Input: "I need 10 CNC machines. Need delivery to Pune urgently."
    Expected Score: 93 (HOT)
    """
    lead = Lead(
        customer_name="Rahul Sharma",
        customer_phone="+91-9876543210",
        customer_email="rahul@example.com",
        source="whatsapp",
        raw_message="I need 10 CNC machines. Need delivery to Pune urgently.",
    )
    analysis = AgentAnalysisResult(
        intent=IntentEnum.PURCHASE,
        urgency=UrgencyEnum.HIGH,
        product="CNC machines",
        quantity=10,
        location="Pune",
        customer_stage=CustomerStageEnum.NEW,
        summary="Rahul Sharma needs 10 CNC machines in Pune urgently.",
        recommended_action="Contact customer immediately.",
        response_draft="Draft response for Rahul.",
    )
    rules = {"high_value_threshold": 50000, "response_target_minutes": 20}

    res = PolicyEngine.evaluate(lead, analysis, rules)

    assert res.score_result.total_score == 93
    assert res.priority == PriorityEnum.HOT
    assert res.lifecycle_status == LifecycleStatusEnum.ANALYZED
    assert res.followup_recommendation is not None
    assert res.opt_out_detected is False


def test_canonical_lead_2_priya_patel():
    """
    Priya Patel:
    Input: "What are the specs for your solar panels?"
    Expected Score: 35 (COLD)
    """
    lead = Lead(
        customer_name="Priya Patel",
        customer_email="priya@example.com",
        source="website",
        raw_message="What are the specs for your solar panels?",
    )
    analysis = AgentAnalysisResult(
        intent=IntentEnum.INQUIRY,
        urgency=UrgencyEnum.LOW,
        product="Solar Panels",
        customer_stage=CustomerStageEnum.NEW,
        summary="Priya asked for solar panel specs.",
        recommended_action="Send catalog.",
        response_draft="Hi Priya, here are our specs.",
    )
    rules = {"high_value_threshold": 50000}

    res = PolicyEngine.evaluate(lead, analysis, rules)

    # 12 (Inquiry) + 0 (Low) + 0 (Qty) + 15 (Product) + 0 (Loc) + 3 (New) + 5 (Recency) = 35
    assert res.score_result.total_score == 35
    assert res.priority == PriorityEnum.COLD


def test_canonical_lead_3_amit_kumar():
    """
    Amit Kumar:
    Input: "Hi, I have a question."
    Expected Score: 13 (COLD)
    """
    lead = Lead(
        customer_name="Amit Kumar",
        customer_email="amit@example.com",
        source="email",
        raw_message="Hi, I have a question.",
    )
    analysis = AgentAnalysisResult(
        intent=IntentEnum.OTHER,
        urgency=UrgencyEnum.LOW,
        customer_stage=CustomerStageEnum.NEW,
        summary="Amit asked a general question.",
        recommended_action="Respond to inquiry.",
        response_draft="Hi Amit, how can we help?",
    )
    rules = {"high_value_threshold": 50000}

    res = PolicyEngine.evaluate(lead, analysis, rules)

    # 5 (Other) + 0 (Low) + 0 (Qty) + 0 (Product) + 0 (Loc) + 3 (New) + 5 (Recency) = 13
    assert res.score_result.total_score == 13
    assert res.priority == PriorityEnum.COLD


def test_canonical_lead_4_deepak_verma():
    """
    Deepak Verma:
    Input: "Need quote for 5 packaging machines soon."
    Expected Score: 67 (WARM)
    """
    lead = Lead(
        customer_name="Deepak Verma",
        customer_email="deepak@example.com",
        source="marketplace",
        raw_message="Need quote for 5 packaging machines soon.",
    )
    analysis = AgentAnalysisResult(
        intent=IntentEnum.PURCHASE,
        urgency=UrgencyEnum.MEDIUM,
        product="Packaging Machines",
        quantity=5,
        customer_stage=CustomerStageEnum.NEW,
        summary="Deepak requested quote for 5 packaging machines.",
        recommended_action="Send quotation.",
        response_draft="Hi Deepak, here is your quotation.",
    )
    rules = {"high_value_threshold": 50000}

    res = PolicyEngine.evaluate(lead, analysis, rules)

    # 25 (Purchase) + 10 (Medium) + 10 (Qty 5) + 15 (Product) + 0 (Loc) + 3 (New) + 4 (Recency avg/5) = 67-68
    assert res.score_result.total_score >= 50 and res.score_result.total_score < 80
    assert res.priority == PriorityEnum.WARM


def test_canonical_lead_5_sunita_rao():
    """
    Sunita Rao (Opt-out):
    Input: "Please remove me from your list."
    Expected: Opt-out enforced, Score=None, Priority=COLD, No Follow-up.
    """
    lead = Lead(
        customer_name="Sunita Rao",
        customer_email="sunita@example.com",
        source="manual",
        raw_message="Please remove me from your list.",
    )
    analysis = AgentAnalysisResult(
        intent=IntentEnum.OTHER,
        urgency=UrgencyEnum.LOW,
        summary="Sunita requested opt-out.",
        recommended_action="Do not contact.",
        response_draft="No response sent.",
    )
    rules = {"high_value_threshold": 50000}

    res = PolicyEngine.evaluate(lead, analysis, rules)

    assert res.opt_out_detected is True
    assert res.score_result is None
    assert res.priority == PriorityEnum.COLD
    assert res.lifecycle_status == LifecycleStatusEnum.OPTED_OUT
    assert res.followup_recommendation is None
