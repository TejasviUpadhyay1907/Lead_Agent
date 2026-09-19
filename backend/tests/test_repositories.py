"""
LeadRescue AI — Repository Integration/Unit Tests (Memory Mode)
"""

import pytest

from app.models.audit import AuditEventCreate
from app.models.config import ConfigUpdate
from app.models.enums import FollowUpStatusEnum, LifecycleStatusEnum, SourceEnum
from app.models.followup import FollowUpCreate, FollowUpUpdate
from app.models.lead import LeadCreate, LeadUpdate
from app.repositories.audit import AuditRepository
from app.repositories.config import ConfigRepository
from app.repositories.followups import FollowUpsRepository
from app.repositories.leads import LeadsRepository


@pytest.fixture
def leads_repo():
    return LeadsRepository(use_memory=True)


@pytest.fixture
def followups_repo():
    return FollowUpsRepository(use_memory=True)


@pytest.fixture
def audit_repo():
    return AuditRepository(use_memory=True)


@pytest.fixture
def config_repo():
    return ConfigRepository(use_memory=True)


def test_leads_repo_crud(leads_repo):
    # Create
    lead_in = LeadCreate(
        customer_name="Rahul Sharma",
        source=SourceEnum.WHATSAPP,
        raw_message="I need 10 CNC machines.",
    )
    created = leads_repo.create(lead_in)
    assert created.lead_id is not None

    # Get
    fetched = leads_repo.get_by_id(created.lead_id)
    assert fetched is not None
    assert fetched.customer_name == "Rahul Sharma"

    # List
    all_leads = leads_repo.list_leads()
    assert len(all_leads) == 1

    # Update
    updated = leads_repo.update(
        created.lead_id,
        LeadUpdate(lifecycle_status=LifecycleStatusEnum.ANALYZED),
    )
    assert updated.lifecycle_status == LifecycleStatusEnum.ANALYZED


def test_followups_repo_crud(followups_repo):
    fup_in = FollowUpCreate(
        lead_id="lead-123",
        action="Send catalog",
        due_at="2026-09-20T12:00:00Z",
    )
    created = followups_repo.create(fup_in)
    assert created.followup_id is not None
    assert created.status == FollowUpStatusEnum.SCHEDULED

    # List by lead
    by_lead = followups_repo.list_followups(lead_id="lead-123")
    assert len(by_lead) == 1

    # Update status
    updated = followups_repo.update(
        created.followup_id,
        FollowUpUpdate(status=FollowUpStatusEnum.COMPLETED),
    )
    assert updated.status == FollowUpStatusEnum.COMPLETED


def test_audit_repo_crud(audit_repo):
    event_in = AuditEventCreate(
        lead_id="lead-123",
        action="lead_received",
        actor="system",
        details={"source": "whatsapp"},
    )
    created = audit_repo.create(event_in)
    assert created.audit_id is not None

    events = audit_repo.list_by_lead("lead-123")
    assert len(events) == 1
    assert events[0].action == "lead_received"


def test_config_repo_crud(config_repo):
    cfg = config_repo.get_config("business_rules")
    assert cfg.config_value["response_target_minutes"] == 20

    updated = config_repo.update_config(
        "business_rules",
        ConfigUpdate(config_value={"response_target_minutes": 30}),
    )
    assert updated.config_value["response_target_minutes"] == 30
