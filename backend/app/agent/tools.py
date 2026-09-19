"""
LeadRescue AI — Read-Only Agent Tools
Defines read-only tools for Strands Agent according to Phase 3 specification.

CRITICAL ARCHITECTURE REQUIREMENT:
- All tools in this file MUST BE READ-ONLY.
- No database mutation, scoring, priority assignment, follow-up creation, or sending tools are exposed to the agent.
"""

from typing import Any, Dict, List, Optional
from strands import tool

from app.api.deps import get_config_repo, get_leads_repo


@tool
def get_lead(lead_id: str) -> Dict[str, Any]:
    """
    Read-only tool: Retrieve raw message, source, and metadata for a specific lead.
    
    Args:
        lead_id: Unique string identifier of the lead.
        
    Returns:
        Dict containing lead_id, customer_name, customer_email, customer_phone, source, and raw_message.
    """
    leads_repo = get_leads_repo()
    lead = leads_repo.get_by_id(lead_id)
    if not lead:
        return {"error": f"Lead with ID '{lead_id}' not found"}

    return {
        "lead_id": lead.lead_id,
        "customer_name": lead.customer_name,
        "customer_email": lead.customer_email,
        "customer_phone": lead.customer_phone,
        "source": lead.source.value if hasattr(lead.source, "value") else str(lead.source),
        "raw_message": lead.raw_message,
        "created_at": lead.created_at,
        "lifecycle_status": lead.lifecycle_status.value if hasattr(lead.lifecycle_status, "value") else str(lead.lifecycle_status),
    }


@tool
def get_customer_history(customer_email: Optional[str] = None, customer_phone: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Read-only tool: Retrieve past interactions/leads for a returning customer based on email or phone.
    
    Args:
        customer_email: Optional email address of the customer.
        customer_phone: Optional phone number of the customer.
        
    Returns:
        List of historical lead summary dicts.
    """
    if not customer_email and not customer_phone:
        return []

    leads_repo = get_leads_repo()
    all_leads = leads_repo.list_leads()

    history = []
    for l in all_leads:
        match = False
        if customer_email and l.customer_email == customer_email:
            match = True
        elif customer_phone and l.customer_phone == customer_phone:
            match = True

        if match:
            history.append({
                "lead_id": l.lead_id,
                "created_at": l.created_at,
                "source": l.source.value if hasattr(l.source, "value") else str(l.source),
                "summary": l.ai_summary or l.raw_message[:100],
                "lifecycle_status": l.lifecycle_status.value if hasattr(l.lifecycle_status, "value") else str(l.lifecycle_status),
            })

    return history


@tool
def get_business_rules() -> Dict[str, Any]:
    """
    Read-only tool: Retrieve official business rules, SLA targets, supported locations, and business parameters.
    
    Returns:
        Dict containing business configuration values.
    """
    config_repo = get_config_repo()
    cfg = config_repo.get_config("business_rules")
    return cfg.config_value
