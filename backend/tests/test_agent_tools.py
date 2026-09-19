"""
LeadRescue AI — Unit Tests for Strands Read-Only Tools
"""

from app.agent.tools import get_business_rules, get_customer_history, get_lead
from app.models.lead import LeadCreate
from app.repositories.leads import LeadsRepository


def test_get_lead_tool(monkeypatch):
    """Test get_lead tool returns raw message and metadata."""
    repo = LeadsRepository(use_memory=True)
    lead = repo.create(LeadCreate(customer_name="Rahul", raw_message="Need 10 CNC machines"))

    # Patch dependency provider to use our test memory repo
    monkeypatch.setattr("app.agent.tools.get_leads_repo", lambda: repo)

    result = get_lead(lead.lead_id)
    assert result["lead_id"] == lead.lead_id
    assert result["customer_name"] == "Rahul"
    assert result["raw_message"] == "Need 10 CNC machines"


def test_get_customer_history_tool(monkeypatch):
    """Test get_customer_history tool returns customer interaction history."""
    repo = LeadsRepository(use_memory=True)
    l1 = repo.create(LeadCreate(customer_name="Rahul", customer_phone="+91-9876543210", raw_message="Lead 1"))
    l2 = repo.create(LeadCreate(customer_name="Rahul", customer_phone="+91-9876543210", raw_message="Lead 2"))

    monkeypatch.setattr("app.agent.tools.get_leads_repo", lambda: repo)

    history = get_customer_history(customer_phone="+91-9876543210")
    assert len(history) == 2


def test_get_business_rules_tool():
    """Test get_business_rules tool returns official business configuration."""
    rules = get_business_rules()
    assert "response_target_minutes" in rules
    assert "business_name" in rules
