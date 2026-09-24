"""
LeadRescue AI — Repository Integration/Unit Tests (Memory Mode)
"""

from decimal import Decimal

import pytest

from app.models.audit import AuditEventCreate
from app.models.config import ConfigUpdate
from app.models.enums import FollowUpStatusEnum, LifecycleStatusEnum, SalesOutcomeEnum, SourceEnum
from app.models.followup import FollowUpCreate, FollowUpUpdate
from app.models.lead import Lead, LeadCreate, LeadUpdate
from app.repositories.audit import AuditRepository
from app.repositories.config import ConfigRepository
from app.repositories.followups import FollowUpsRepository
from app.repositories.leads import LeadsRepository, _lead_storage_item, _serialize_item


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


def test_sales_value_is_serialized_as_exact_dynamodb_number():
    lead = Lead(
        customer_name="Won Deal",
        source=SourceEnum.WEBSITE,
        raw_message="Please send a quote.",
        sales_outcome=SalesOutcomeEnum.WON,
        sales_value=Decimal("125000.50"),
        sales_currency="INR",
    )

    encoded = _serialize_item(_lead_storage_item(lead, json_mode=True))

    assert encoded["sales_value"]["N"] == "125000.50"


def test_outcome_report_pages_complete_date_cohorts_and_keep_currencies_separate():
    repo = LeadsRepository(use_memory=True)
    cohort = [
        Lead(customer_name="Won One", source=SourceEnum.WEBSITE, raw_message="quote", created_at="2026-01-02T12:00:00+00:00", sales_outcome=SalesOutcomeEnum.WON, sales_value=Decimal("100.25"), sales_currency="INR"),
        Lead(customer_name="Won Two", source=SourceEnum.WEBSITE, raw_message="quote", created_at="2026-01-03T12:00:00+00:00", sales_outcome=SalesOutcomeEnum.WON, sales_value=Decimal("9.75"), sales_currency="USD"),
        Lead(customer_name="Lost", source=SourceEnum.WEBSITE, raw_message="quote", created_at="2026-01-04T12:00:00+00:00", sales_outcome=SalesOutcomeEnum.LOST),
        Lead(customer_name="Open", source=SourceEnum.WEBSITE, raw_message="quote", created_at="2026-01-05T12:00:00+00:00"),
        Lead(customer_name="Outside", source=SourceEnum.WEBSITE, raw_message="quote", created_at="2026-02-01T12:00:00+00:00", sales_outcome=SalesOutcomeEnum.WON, sales_value=Decimal("999"), sales_currency="INR"),
        Lead(customer_name="Other tenant", source=SourceEnum.WEBSITE, raw_message="quote", created_at="2026-01-06T12:00:00+00:00", tenant_id="other-tenant", sales_outcome=SalesOutcomeEnum.WON, sales_value=Decimal("500"), sales_currency="INR"),
    ]
    repo._memory_store = {lead.lead_id: lead for lead in cohort}

    first = repo.outcome_report_page("2026-01-01T00:00:00+00:00", "2026-01-31T23:59:59+00:00", limit=2)
    second = repo.outcome_report_page(
        "2026-01-01T00:00:00+00:00", "2026-01-31T23:59:59+00:00", cursor=first["next_cursor"], limit=2,
    )

    assert first["counts"] == {"total": 2, "won": 2, "lost": 0, "disqualified": 0, "open": 0}
    assert first["won_value_by_currency"] == {"INR": "100.25", "USD": "9.75"}
    assert second["counts"] == {"total": 2, "won": 0, "lost": 1, "disqualified": 0, "open": 1}
    assert second["won_value_by_currency"] == {}
    assert second["next_cursor"] is None

    with pytest.raises(ValueError, match="does not match"):
        repo.outcome_report_page("2026-01-02T00:00:00+00:00", "2026-01-31T23:59:59+00:00", cursor=first["next_cursor"], limit=2)


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
