"""
LeadRescue AI — Strands Agent Orchestration & Canonical Tests
"""

from app.agent.lead_agent import LeadRescueAgent, is_aws_credentials_available
from app.models.enums import CustomerStageEnum, IntentEnum, UrgencyEnum
from app.models.lead import LeadCreate
from app.repositories.leads import LeadsRepository


def test_canonical_rahul_understanding(monkeypatch):
    """
    Canonical Lead 1 (Rahul Sharma):
    Input: "I need 10 CNC machines. Need delivery to Pune urgently."
    Verifies agent extracts intent=purchase, urgency=high, product=CNC machines, quantity=10, location=Pune.
    Verifies agent does NOT calculate score or priority.
    """
    repo = LeadsRepository(use_memory=True)
    rahul_lead = repo.create(
        LeadCreate(
            customer_name="Rahul Sharma",
            customer_phone="+91-9876543210",
            customer_email="rahul@example.com",
            source="whatsapp",
            raw_message="I need 10 CNC machines. Need delivery to Pune urgently.",
        )
    )

    monkeypatch.setattr("app.agent.tools.get_leads_repo", lambda: repo)

    agent = LeadRescueAgent()
    result, events = agent.analyze_lead(rahul_lead.lead_id)

    # Understanding assertions
    assert result.intent == IntentEnum.PURCHASE
    assert result.urgency == UrgencyEnum.HIGH
    assert result.product == "CNC machines"
    assert result.quantity == 10
    assert result.location == "Pune"
    assert result.customer_stage == CustomerStageEnum.NEW
    assert "CNC machines" in result.key_entities

    # Deterministic fields MUST NOT exist on AgentAnalysisResult
    assert not hasattr(result, "score")
    assert not hasattr(result, "priority")
    assert not hasattr(result, "risk_status")

    # Observability events logged
    event_names = [e["event"] for e in events]
    assert "tool_start" in event_names
    assert "tool_end" in event_names
    assert "agent_start" in event_names


def test_canonical_sunita_opt_out(monkeypatch):
    """
    Canonical Lead 5 (Sunita Rao):
    Input: "Please remove me from your list."
    Agent should process context without mutating DB or executing workflow directly.
    """
    repo = LeadsRepository(use_memory=True)
    sunita_lead = repo.create(
        LeadCreate(
            customer_name="Sunita Rao",
            customer_email="sunita@example.com",
            source="manual",
            raw_message="Please remove me from your list.",
        )
    )

    monkeypatch.setattr("app.agent.tools.get_leads_repo", lambda: repo)

    agent = LeadRescueAgent()
    result, events = agent.analyze_lead(sunita_lead.lead_id)

    # Result contains analysis
    assert result.summary is not None
    assert result.response_draft is not None

    # Verify agent did NOT mutate repository directly
    fetched = repo.get_by_id(sunita_lead.lead_id)
    # The agent itself does not alter the repository
    assert fetched.score is None


def test_aws_credential_gate_check():
    """Verify is_aws_credentials_available returns boolean without crashing."""
    result = is_aws_credentials_available()
    assert isinstance(result, bool)
