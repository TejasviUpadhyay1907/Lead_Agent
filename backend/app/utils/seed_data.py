"""
LeadRescue AI — Synthetic Seed Data Helper
Provides the 5 canonical Phase 0 test leads for demonstration and testing.
"""

from typing import List
from app.models.enums import LifecycleStatusEnum, SourceEnum
from app.models.lead import LeadCreate


CANONICAL_LEADS_DATA = [
    {
        "customer_name": "Rahul Sharma",
        "customer_phone": "+91-9876543210",
        "customer_email": "rahul.sharma@example.com",
        "source": SourceEnum.WHATSAPP,
        "raw_message": "I need 10 CNC machines. Need delivery to Pune urgently.",
    },
    {
        "customer_name": "Priya Patel",
        "customer_email": "priya.patel@example.com",
        "source": SourceEnum.WEBSITE,
        "raw_message": "Can you share your product catalog for solar panels?",
    },
    {
        "customer_name": "Amit Kumar",
        "customer_email": "amit.kumar@example.com",
        "source": SourceEnum.EMAIL,
        "raw_message": "What industries do you serve?",
    },
    {
        "customer_name": "Deepak Verma",
        "customer_phone": "+91-9812345678",
        "source": SourceEnum.PHONE,
        "raw_message": "We discussed 5 packaging machines last week. Still waiting for quote.",
    },
    {
        "customer_name": "Sunita Rao",
        "customer_email": "sunita.rao@example.com",
        "source": SourceEnum.MANUAL,
        "raw_message": "Please remove me from your list.",
    },
]


def get_canonical_lead_creates() -> List[LeadCreate]:
    """Returns LeadCreate objects for the 5 canonical leads."""
    return [LeadCreate(**lead) for lead in CANONICAL_LEADS_DATA]
