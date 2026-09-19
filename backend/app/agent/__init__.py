"""
LeadRescue AI — Agent Package Initialization
Exposes LeadRescueAgent, read-only tools, and system prompt.
"""

from app.agent.lead_agent import LeadRescueAgent, is_aws_credentials_available
from app.agent.prompts import LEAD_RESCUE_SYSTEM_PROMPT
from app.agent.tools import get_business_rules, get_customer_history, get_lead

__all__ = [
    "LeadRescueAgent",
    "is_aws_credentials_available",
    "get_lead",
    "get_customer_history",
    "get_business_rules",
    "LEAD_RESCUE_SYSTEM_PROMPT",
]
