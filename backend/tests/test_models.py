"""
LeadRescue AI — Unit Tests for Domain Models
"""

import pytest
from pydantic import ValidationError

from app.models.enums import LifecycleStatusEnum, PriorityEnum, SourceEnum
from app.models.followup import FollowUpCreate
from app.models.lead import Lead, LeadCreate, LeadUpdate


def test_valid_lead_create():
    lead_create = LeadCreate(
        customer_name="Rahul Sharma",
        customer_phone="+91-9876543210",
        source=SourceEnum.WHATSAPP,
        raw_message="I need 10 CNC machines.",
    )
    assert lead_create.customer_name == "Rahul Sharma"
    assert lead_create.source == SourceEnum.WHATSAPP


def test_lead_create_rejects_extra_fields():
    """Client cannot submit score or priority on creation."""
    with pytest.raises(ValidationError):
        LeadCreate(
            customer_name="Rahul Sharma",
            raw_message="Test message",
            score=99,  # Forbidden field
        )


def test_invalid_source_enum():
    with pytest.raises(ValidationError):
        LeadCreate(
            customer_name="Test",
            source="invalid_channel",  # Invalid enum value
            raw_message="Test message",
        )


def test_full_lead_default_values():
    lead = Lead(
        customer_name="Priya Patel",
        raw_message="Need solar panel info",
    )
    assert lead.lead_id is not None
    assert lead.lifecycle_status == LifecycleStatusEnum.NEW
    assert lead.score is None
    assert lead.priority is None


def test_followup_create_validation():
    fup = FollowUpCreate(
        lead_id="test-id",
        action="Call customer",
        due_at="2026-09-20T10:00:00Z",
    )
    assert fup.action == "Call customer"
