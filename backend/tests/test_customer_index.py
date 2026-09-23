import pytest

from app.config.settings import settings
from app.repositories.customer_index import _cached_index_hmac_key, customer_index_keys
from app.models.lead import Lead
from app.repositories.leads import LeadsRepository


def test_hmac_customer_indexes_are_stable_and_normalized():
    key = b"a" * 32

    first = customer_index_keys("tenant-a", " Sales@Example.com ", "+1 (555) 123-4567", hmac_key=key)
    normalized = customer_index_keys("tenant-a", "sales@example.com", "15551234567", hmac_key=key)

    assert first == normalized


def test_hmac_customer_indexes_are_scoped_by_tenant_and_secret():
    first = customer_index_keys("tenant-a", "sales@example.com", "15551234567", hmac_key=b"a" * 32)
    other_tenant = customer_index_keys("tenant-b", "sales@example.com", "15551234567", hmac_key=b"a" * 32)
    rotated_secret = customer_index_keys("tenant-a", "sales@example.com", "15551234567", hmac_key=b"b" * 32)

    assert first["tenant_email_key"] != other_tenant["tenant_email_key"]
    assert first["tenant_email_key"] != rotated_secret["tenant_email_key"]


def test_hmac_indexes_do_not_contain_the_contact_identifiers():
    keys = customer_index_keys("tenant-a", "sales@example.com", "+1 555 123 4567", hmac_key=b"a" * 32)

    assert "sales@example.com" not in keys["tenant_email_key"]
    assert "15551234567" not in keys["tenant_phone_key"]


def test_production_indexing_fails_closed_without_secret(monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "customer_index_secret_arn", "")
    _cached_index_hmac_key.cache_clear()

    with pytest.raises(RuntimeError, match="HMAC secret is not configured"):
        customer_index_keys("tenant-a", "sales@example.com", None)


def test_contacts_without_identifiers_do_not_need_index_secret(monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "customer_index_secret_arn", "")

    assert customer_index_keys("tenant-a", "  ", "---") == {
        "tenant_email_key": None,
        "tenant_phone_key": None,
    }


class _PagedLeadTable:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def query(self, **kwargs):
        self.calls.append(kwargs)
        return next(self.responses)


@pytest.mark.parametrize(
    ("identifier_type", "index_name", "key_name"),
    [
        ("email", "tenant-email-index", "tenant_email_key"),
        ("phone", "tenant-phone-index", "tenant_phone_key"),
    ],
)
def test_customer_record_discovery_queries_tenant_gsi_with_tenant_filter_and_cursor(
    monkeypatch, identifier_type, index_name, key_name,
):
    tenant = settings.effective_tenant_id
    monkeypatch.setattr(
        "app.repositories.leads.customer_index_keys",
        lambda *_args, **_kwargs: {
            "tenant_email_key": f"{tenant}#email-key",
            "tenant_phone_key": f"{tenant}#phone-key",
        },
    )
    matching = Lead(
        lead_id="matching-lead", tenant_id=tenant, customer_name="Customer",
        customer_email="customer@example.com", raw_message="A private message", source="website",
    ).model_dump(mode="json")
    next_matching = {**matching, "lead_id": "next-matching-lead", "created_at": "2026-09-23T12:00:00+00:00"}
    other_tenant = {**matching, "lead_id": "foreign-lead", "tenant_id": "other-tenant"}
    last_key = {
        "lead_id": "matching-lead",
        "tenant_id": tenant,
        "created_at": matching["created_at"],
        key_name: f"{tenant}#{'email' if identifier_type == 'email' else 'phone'}-key",
    }
    table = _PagedLeadTable([
        {"Items": [matching, other_tenant], "LastEvaluatedKey": last_key},
        {"Items": [next_matching]},
    ])
    repository = LeadsRepository(use_memory=True)
    repository.use_memory = False
    repository._table = table

    first_page, cursor = repository.find_customer_history_page(
        identifier_type=identifier_type,
        customer_email="customer@example.com",
        customer_phone="+1-555-123-4567",
        limit=1,
    )
    second_page, next_cursor = repository.find_customer_history_page(
        identifier_type=identifier_type,
        customer_email="customer@example.com",
        customer_phone="+1-555-123-4567",
        limit=1,
        cursor=cursor,
    )

    assert [lead.lead_id for lead in first_page] == ["matching-lead"]
    assert [lead.lead_id for lead in second_page] == ["next-matching-lead"]
    assert next_cursor is None
    assert table.calls[0]["IndexName"] == index_name
    assert table.calls[0]["Limit"] == 1
    assert table.calls[1]["ExclusiveStartKey"] == last_key
