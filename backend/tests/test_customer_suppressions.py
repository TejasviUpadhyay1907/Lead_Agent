from types import SimpleNamespace

import pytest

from app.config.settings import settings
from app.models.enums import LifecycleStatusEnum, SourceEnum
from app.models.lead import Lead
from app.repositories.customer_suppressions import suppression_keys
from app.repositories.leads import LeadsRepository, SuppressionRegistryUnavailableError


def _lead(email: str, phone: str) -> Lead:
    return Lead(
        customer_name="Test Customer",
        customer_email=email,
        customer_phone=phone,
        source=SourceEnum.WEBSITE,
        raw_message="Please contact me about pricing.",
    )


class FakeBatchClient:
    def __init__(self, found_keys=(), unprocessed_once=False, always_unprocessed=False):
        self.found_keys = set(found_keys)
        self.unprocessed_once = unprocessed_once
        self.always_unprocessed = always_unprocessed
        self.calls = []

    def batch_get_item(self, RequestItems):
        table_name, request = next(iter(RequestItems.items()))
        self.calls.append(request)
        keys = request["Keys"]
        if self.always_unprocessed or (self.unprocessed_once and len(self.calls) == 1):
            return {"Responses": {table_name: []}, "UnprocessedKeys": {table_name: request}}
        return {
            "Responses": {
                table_name: [
                    {"suppression_key": {"S": item["suppression_key"]["S"]}}
                    for item in keys
                    if item["suppression_key"]["S"] in self.found_keys
                ]
            }
        }


class UnavailableBatchClient:
    def batch_get_item(self, RequestItems):
        raise OSError("simulated DynamoDB outage")


def _dynamodb_repository(monkeypatch, client):
    table_name = "test-customer-suppressions"
    monkeypatch.setattr(settings, "customer_suppressions_table", table_name)
    repo = LeadsRepository(use_memory=True)
    repo.use_memory = False
    repo._suppressions_table = SimpleNamespace(meta=SimpleNamespace(client=client))
    repo._suppressions_ready = True
    return repo


def test_memory_batch_lookup_matches_contact_suppression():
    repo = LeadsRepository(use_memory=True)
    prior = _lead("opted@example.com", "+1 555 111 2222")
    prior.lifecycle_status = LifecycleStatusEnum.OPTED_OUT
    repo._memory_store[prior.lead_id] = prior
    matching = _lead("OPTED@example.com", "+1 (555) 111-2222")
    other = _lead("other@example.com", "+1 555 333 4444")

    assert repo.customer_opted_out_many([matching, other]) == {matching.lead_id}


def test_demo_repository_does_not_initialize_cloud_storage(monkeypatch):
    import app.repositories.leads as leads_module

    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "app_env", "local")
    monkeypatch.setattr(
        leads_module,
        "get_boto3_dynamodb_resource",
        lambda: pytest.fail("demo mode must not initialize a cloud database"),
    )

    repo = LeadsRepository()

    assert repo.use_memory is True
    assert repo._table is None
    assert repo._suppressions_table is None


def test_suppression_migration_read_is_lazy_and_fails_closed(monkeypatch):
    from app.repositories.leads import SuppressionMigrationIncompleteError

    repo = LeadsRepository(use_memory=True)
    calls = []
    repo.use_memory = False
    repo._suppressions_ready = False
    repo._suppressions_table = SimpleNamespace(
        get_item=lambda **kwargs: calls.append(kwargs) or {},
    )

    assert calls == []
    with pytest.raises(SuppressionMigrationIncompleteError):
        repo._ensure_suppressions_ready()
    assert calls and calls[0]["ConsistentRead"] is True


def test_legacy_unkeyed_suppression_marker_does_not_open_readiness():
    from app.repositories.leads import SuppressionMigrationIncompleteError

    repo = LeadsRepository(use_memory=True)
    repo.use_memory = False
    repo._suppressions_ready = False
    repo._suppressions_table = SimpleNamespace(
        get_item=lambda **kwargs: {
            "Item": {"suppression_key": kwargs["Key"]["suppression_key"], "index_key_scheme": "sha256-v0"}
        },
    )

    with pytest.raises(SuppressionMigrationIncompleteError):
        repo._ensure_suppressions_ready()


def test_marker_from_different_hmac_key_does_not_open_readiness(monkeypatch):
    from app.repositories.customer_index import require_customer_index_key
    from app.repositories.leads import SuppressionMigrationIncompleteError

    repo = LeadsRepository(use_memory=True)
    repo.use_memory = False
    repo._suppressions_ready = False
    repo._suppressions_table = SimpleNamespace(
        get_item=lambda **kwargs: {
            "Item": {
                "suppression_key": kwargs["Key"]["suppression_key"],
                "index_key_scheme": "hmac-sha256-v1",
                "index_key_id": "a-different-key",
            }
        },
    )
    monkeypatch.setattr("app.repositories.leads.require_customer_index_key", lambda: require_customer_index_key())

    with pytest.raises(SuppressionMigrationIncompleteError):
        repo._ensure_suppressions_ready()


def test_readiness_requires_both_migrations_for_the_active_key():
    from app.repositories.customer_index import require_customer_index_key
    from app.repositories.customer_suppressions import history_index_marker_key, migration_marker_key

    tenant_id = settings.effective_tenant_id
    key_id = require_customer_index_key()
    markers = {
        migration_marker_key(tenant_id): {
            "index_key_scheme": "hmac-sha256-v1",
            "index_key_id": key_id,
        },
        history_index_marker_key(tenant_id): {
            "index_key_scheme": "hmac-sha256-v1",
            "index_key_id": key_id,
        },
    }
    repo = LeadsRepository(use_memory=True)
    repo.use_memory = False
    repo._suppressions_ready = False
    repo._suppressions_table = SimpleNamespace(
        get_item=lambda **kwargs: {"Item": markers.get(kwargs["Key"]["suppression_key"])},
    )

    repo._ensure_suppressions_ready()

    assert repo._suppressions_ready is True


def test_dynamodb_batch_lookup_deduplicates_and_chunks_to_100(monkeypatch):
    leads = [_lead(f"customer-{i}@example.com", f"+1 555 {i:07d}") for i in range(51)]
    all_keys = [
        key
        for lead in leads
        for key in suppression_keys(settings.effective_tenant_id, lead.customer_email, lead.customer_phone)
    ]
    suppressed_key = all_keys[-1]
    client = FakeBatchClient(found_keys={suppressed_key})
    repo = _dynamodb_repository(monkeypatch, client)

    result = repo.customer_opted_out_many(leads)

    assert result == {leads[-1].lead_id}
    assert [len(call["Keys"]) for call in client.calls] == [100, 2]
    assert all(call["ConsistentRead"] is True for call in client.calls)
    assert all(call["ProjectionExpression"] == "suppression_key" for call in client.calls)


def test_dynamodb_batch_lookup_retries_unprocessed_keys(monkeypatch):
    lead = _lead("retry@example.com", "+1 555 000 0001")
    key = suppression_keys(settings.effective_tenant_id, lead.customer_email, lead.customer_phone)[0]
    client = FakeBatchClient(found_keys={key}, unprocessed_once=True)
    repo = _dynamodb_repository(monkeypatch, client)
    monkeypatch.setattr("app.repositories.leads.time.sleep", lambda _delay: None)

    assert repo.customer_opted_out_many([lead]) == {lead.lead_id}
    assert len(client.calls) == 2


def test_dynamodb_batch_lookup_fails_closed_after_unprocessed_retries(monkeypatch):
    lead = _lead("busy@example.com", "+1 555 000 0002")
    client = FakeBatchClient(always_unprocessed=True)
    repo = _dynamodb_repository(monkeypatch, client)
    monkeypatch.setattr("app.repositories.leads.time.sleep", lambda _delay: None)

    with pytest.raises(SuppressionRegistryUnavailableError, match="did not process all customer suppression lookups"):
        repo.customer_opted_out_many([lead])
    assert len(client.calls) == 5


def test_dynamodb_batch_lookup_outage_is_explicitly_unavailable(monkeypatch):
    lead = _lead("offline@example.com", "+1 555 000 0003")
    repo = _dynamodb_repository(monkeypatch, UnavailableBatchClient())

    with pytest.raises(SuppressionRegistryUnavailableError):
        repo.customer_opted_out_many([lead])
