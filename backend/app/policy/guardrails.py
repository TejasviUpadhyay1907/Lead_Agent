"""
LeadRescue AI — Policy Guardrails & Stop Conditions
Enforces opt-out detection and hard business rules independently of LLM reasoning.
"""

from typing import List, Tuple
from app.models.enums import LifecycleStatusEnum

OPT_OUT_KEYWORDS = [
    "remove me",
    "stop contacting",
    "stop contact",
    "unsubscribe",
    "don't contact",
    "dont contact",
    "opt out",
    "opt-out",
    "please delete",
]


def check_opt_out(raw_message: str) -> Tuple[bool, str]:
    """
    Deterministically scans raw message for opt-out keywords.
    """
    msg_lower = raw_message.lower()
    for kw in OPT_OUT_KEYWORDS:
        if kw in msg_lower:
            return True, f"Matched opt-out phrase '{kw}'"
    return False, "No opt-out phrases detected"
