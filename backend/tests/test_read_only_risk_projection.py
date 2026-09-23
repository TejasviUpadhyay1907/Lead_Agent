from fastapi import Response

from app.api import leads as leads_api
from app.models.enums import LifecycleStatusEnum, RiskStatusEnum, SourceEnum
from app.models.lead import LeadCreate
from app.repositories.config import ConfigRepository
from app.repositories.leads import LeadsRepository


def test_list_and_detail_return_current_risk_without_mutating_stored_lead(monkeypatch):
    leads_repo = LeadsRepository(use_memory=True)
    config_repo = ConfigRepository(use_memory=True)
    lead = leads_repo.create(
        LeadCreate(
            customer_name="Read Only Risk Test",
            source=SourceEnum.WEBSITE,
            raw_message="Please send product details.",
        )
    )
    original_updated_at = lead.updated_at
    monkeypatch.setattr(
        leads_api,
        "evaluate_risk",
        lambda _lead, _rules: (RiskStatusEnum.AT_RISK, "2026-09-23T00:00:00+00:00"),
    )

    listed = leads_api.list_leads(
        Response(),
        {"sub": "test-operator"},
        None,
        None,
        None,
        None,
        50,
        None,
        leads_repo,
        config_repo,
    )
    stored_after_list = leads_repo.get_by_id(lead.lead_id)

    assert listed[0].risk_status == RiskStatusEnum.AT_RISK
    assert stored_after_list.risk_status == RiskStatusEnum.NORMAL
    assert stored_after_list.lifecycle_status == LifecycleStatusEnum.NEW
    assert stored_after_list.updated_at == original_updated_at

    detailed = leads_api.get_lead(lead.lead_id, {"sub": "test-operator"}, leads_repo, config_repo)
    stored_after_detail = leads_repo.get_by_id(lead.lead_id)

    assert detailed.risk_status == RiskStatusEnum.AT_RISK
    assert stored_after_detail.risk_status == RiskStatusEnum.NORMAL
    assert stored_after_detail.lifecycle_status == LifecycleStatusEnum.NEW
    assert stored_after_detail.updated_at == original_updated_at
