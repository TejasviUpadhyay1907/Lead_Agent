import pytest

from app.config.settings import settings
from app.repositories.customer_index import _cached_index_hmac_key, customer_index_keys


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
