from urllib.parse import parse_qs, urlsplit
from urllib.request import Request

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.security import require_authenticated_user
from app.integrations import zoho_oauth
from app.main import app


def _config():
    return {
        "client_id": "client-id",
        "client_secret": "client-secret",
        "accounts_url": "https://accounts.zoho.in",
        "redirect_uri": "https://api.example.com/integrations/v1/zoho/oauth/callback",
    }


def test_authorization_url_uses_offline_lead_update_scope_and_single_use_state(monkeypatch):
    stored = []
    monkeypatch.setattr(zoho_oauth, "load_oauth_config", _config)
    monkeypatch.setattr(zoho_oauth, "_store_oauth_state", lambda state, _actor: stored.append(state))

    url, state = zoho_oauth.create_authorization_url("admin-sub")
    query = parse_qs(urlsplit(url).query)

    assert query == {
        "scope": ["ZohoCRM.modules.leads.READ,ZohoCRM.modules.leads.UPDATE,ZohoCRM.settings.fields.READ"],
        "client_id": ["client-id"],
        "response_type": ["code"],
        "access_type": ["offline"],
        "redirect_uri": [_config()["redirect_uri"]],
        "state": [state],
    }
    assert len(state) >= 32
    assert stored == [state]


def test_oauth_configuration_rejects_non_zoho_accounts_and_insecure_redirect(monkeypatch):
    monkeypatch.setattr(zoho_oauth.settings, "zoho_oauth_secret_arn", "secret-arn")

    class SecretClient:
        def get_secret_value(self, **_kwargs):
            config = _config()
            config["accounts_url"] = "https://attacker.example"
            return {"SecretString": __import__("json").dumps(config)}

    monkeypatch.setattr(zoho_oauth, "_secrets_client", lambda: SecretClient())
    with pytest.raises(HTTPException) as exc:
        zoho_oauth.load_oauth_config()
    assert exc.value.status_code == 503


def test_token_exchange_keeps_credentials_in_post_body_and_checks_api_domain(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return b'{"access_token":"access","refresh_token":"refresh","api_domain":"https://www.zohoapis.in"}'

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(zoho_oauth, "_urlopen_no_redirect", fake_urlopen)
    response = zoho_oauth.exchange_authorization_code(_config(), "grant-code")

    assert response["refresh_token"] == "refresh"
    assert captured["timeout"] == 8
    assert "client_secret" not in captured["request"].full_url
    assert b"client_secret=client-secret" in captured["request"].data
    assert b"code=grant-code" in captured["request"].data


def test_refresh_access_token_caches_for_one_process_and_validates_domain(monkeypatch):
    zoho_oauth._access_token = None
    zoho_oauth._access_token_expires_at = 0
    zoho_oauth._access_token_api_domain = None
    calls = []

    def refresh(_url, params):
        calls.append(params)
        return {
            "access_token": "access-token",
            "api_domain": "https://www.zohoapis.in",
            "expires_in": 3600,
        }

    monkeypatch.setattr(zoho_oauth, "_token_request", refresh)
    config = {**_config(), "refresh_token": "refresh-token"}

    first = zoho_oauth.refresh_access_token(config)
    second = zoho_oauth.refresh_access_token(config)

    assert first == second == ("access-token", "https://www.zohoapis.in")
    assert len(calls) == 1
    assert calls[0]["grant_type"] == "refresh_token"


def test_connect_consumes_state_and_stores_only_refresh_token_and_api_domain(monkeypatch):
    saved = []
    state_updates = []
    config = _config()
    monkeypatch.setattr(zoho_oauth, "_claim_oauth_state", lambda state: state == "s" * 40)
    monkeypatch.setattr(zoho_oauth, "load_oauth_config", lambda: dict(config))
    monkeypatch.setattr(zoho_oauth, "exchange_authorization_code", lambda _config, _code: {
        "access_token": "short-lived-access",
        "refresh_token": "long-lived-refresh",
        "api_domain": "https://www.zohoapis.in",
    })
    monkeypatch.setattr(zoho_oauth, "save_oauth_config", lambda value: saved.append(dict(value)))
    monkeypatch.setattr(zoho_oauth, "_finish_oauth_state", lambda _state, status: state_updates.append(status))

    zoho_oauth.connect_with_authorization_code("s" * 40, "grant-code")

    assert saved[0]["refresh_token"] == "long-lived-refresh"
    assert saved[0]["api_domain"] == "https://www.zohoapis.in"
    assert saved[0]["requested_scopes"] == zoho_oauth.ZOHO_LEAD_UPDATE_SCOPE.split(",")
    assert "access_token" not in saved[0]
    assert state_updates == ["OAUTH_CONNECTED"]


def test_disconnect_disables_locally_and_keeps_retryable_revocation_state(monkeypatch):
    saved = []
    source = {**_config(), "refresh_token": "refresh-secret", "api_domain": "https://www.zohoapis.in",
             "connected_at": "2026-10-10T00:00:00+00:00", "outcome_writeback_enabled": True}
    revoke_calls = []

    def load():
        return dict(saved[-1] if saved else source)

    def revoke(config, token):
        revoke_calls.append(token)
        if len(revoke_calls) == 1:
            raise zoho_oauth.ZohoOAuthError("temporary failure")

    monkeypatch.setattr(zoho_oauth, "load_oauth_config", load)
    monkeypatch.setattr(zoho_oauth, "save_oauth_config", lambda value: saved.append(dict(value)))
    monkeypatch.setattr(zoho_oauth, "revoke_refresh_token", revoke)

    first = zoho_oauth.disconnect_zoho()
    assert first == {"connection_status": "revocation_pending", "provider_revocation": "pending"}
    assert "refresh_token" not in saved[-1]
    assert saved[-1]["pending_revocation_token"] == "refresh-secret"
    assert saved[-1]["outcome_writeback_enabled"] is False
    assert "api_domain" not in saved[-1] and "connected_at" not in saved[-1]
    assert zoho_oauth.connection_status()["connection_status"] == "revocation_pending"

    second = zoho_oauth.disconnect_zoho()
    assert second == {"connection_status": "not_connected", "provider_revocation": "confirmed"}
    assert "pending_revocation_token" not in saved[-1]
    assert revoke_calls == ["refresh-secret", "refresh-secret"]


def test_revocation_uses_region_specific_post_without_redirect(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return b'{"status":"success"}'

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(zoho_oauth, "_urlopen_no_redirect", fake_urlopen)
    zoho_oauth.revoke_refresh_token(_config(), "refresh/secret")

    request = captured["request"]
    assert request.full_url.startswith("https://accounts.zoho.in/oauth/v2/token/revoke?")
    assert "refresh%2Fsecret" in request.full_url
    assert request.get_method() == "POST"
    assert request.data == b""
    assert captured["timeout"] == 8


def test_field_metadata_returns_only_safe_writable_custom_fields(monkeypatch):
    config = {
        **_config(),
        "refresh_token": "refresh-token",
        "requested_scopes": zoho_oauth.ZOHO_LEAD_UPDATE_SCOPE.split(","),
    }
    monkeypatch.setattr(zoho_oauth, "load_oauth_config", lambda: dict(config))
    monkeypatch.setattr(zoho_oauth, "refresh_access_token", lambda _config: ("access-token", "https://www.zohoapis.in"))
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            import json
            return json.dumps({"fields": [
                {
                    "api_name": "Rescue_Outcome", "field_label": "Rescue Outcome", "data_type": "picklist",
                    "custom_field": True, "read_only": False, "field_read_only": False,
                    "system_mandatory": False, "operation_type": {"api_update": True},
                    "pick_list_values": [{"actual_value": value} for value in ["won", "lost", "disqualified"]],
                },
                {
                    "api_name": "Email", "field_label": "Email", "data_type": "email",
                    "custom_field": False, "operation_type": {"api_update": True},
                },
                {
                    "api_name": "Private_Field", "field_label": "Private", "data_type": "text",
                    "custom_field": True, "operation_type": {"api_update": True},
                    "private": {"restricted": True},
                },
                {
                    "api_name": "Read_Only", "field_label": "Read Only", "data_type": "text",
                    "custom_field": True, "operation_type": {"api_update": False},
                },
                {
                    "api_name": "Case_Mismatch", "field_label": "Case Mismatch", "data_type": "picklist",
                    "custom_field": True, "operation_type": {"api_update": True},
                    "pick_list_values": [{"actual_value": value} for value in ["Won", "Lost", "Disqualified"]],
                },
                {
                    "api_name": "Unused_Outcome", "field_label": "Unused Outcome", "data_type": "picklist",
                    "custom_field": True, "operation_type": {"api_update": True},
                    "pick_list_values": [{"actual_value": value, "type": "unused"} for value in ["won", "lost", "disqualified"]],
                },
            ]}).encode()

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(zoho_oauth, "_urlopen_no_redirect", fake_urlopen)
    fields = zoho_oauth.list_writable_lead_fields()

    assert [field["api_name"] for field in fields] == ["Rescue_Outcome"]
    assert fields[0]["eligible_for"] == ["outcome"]
    assert "module=Leads" in captured["request"].full_url
    assert "Zoho-oauthtoken access-token" == captured["request"].get_header("Authorization")
    assert captured["timeout"] == 8


def test_field_metadata_requires_explicit_new_scope(monkeypatch):
    config = {**_config(), "refresh_token": "refresh-token", "requested_scopes": ["ZohoCRM.modules.leads.READ"]}
    monkeypatch.setattr(zoho_oauth, "load_oauth_config", lambda: config)
    with pytest.raises(HTTPException) as exc:
        zoho_oauth.list_writable_lead_fields()
    assert exc.value.status_code == 409
    assert "Reconnect" in exc.value.detail


def test_outcome_mapping_saves_only_compatible_metadata_fields(monkeypatch):
    config = {**_config(), "refresh_token": "refresh-token", "outcome_writeback_enabled": False}
    saved = []
    fields = [
        {"api_name": "Rescue_Outcome", "eligible_for": ["outcome"]},
        {"api_name": "Rescue_Amount", "eligible_for": ["sales_value"]},
    ]
    monkeypatch.setattr(zoho_oauth, "load_oauth_config", lambda: dict(config))
    monkeypatch.setattr(zoho_oauth, "list_writable_lead_fields", lambda _config: fields)
    monkeypatch.setattr(zoho_oauth, "save_oauth_config", lambda value: saved.append(dict(value)))

    result = zoho_oauth.update_outcome_field_mapping(True, {
        "outcome": "Rescue_Outcome", "sales_value": "Rescue_Amount",
    })

    assert saved[0]["outcome_writeback_enabled"] is True
    assert saved[0]["outcome_field_mapping"] == {"outcome": "Rescue_Outcome", "sales_value": "Rescue_Amount"}
    assert result["outcome_writeback_enabled"] is True


def test_outcome_mapping_rejects_incompatible_or_reused_fields(monkeypatch):
    config = {**_config(), "refresh_token": "refresh-token"}
    monkeypatch.setattr(zoho_oauth, "load_oauth_config", lambda: dict(config))
    monkeypatch.setattr(zoho_oauth, "list_writable_lead_fields", lambda _config: [
        {"api_name": "Rescue_Outcome", "eligible_for": ["outcome"]},
    ])
    with pytest.raises(HTTPException) as incompatible:
        zoho_oauth.update_outcome_field_mapping(True, {"outcome": "Rescue_Outcome", "reason": "Rescue_Outcome"})
    assert incompatible.value.status_code == 422
    assert "distinct" in incompatible.value.detail


def test_public_callback_rejects_replayed_authorization_state(monkeypatch):
    monkeypatch.setattr(
        "app.api.zoho_oauth.connect_with_authorization_code",
        lambda *_args: (_ for _ in ()).throw(HTTPException(status_code=400, detail="state already used")),
    )
    response = TestClient(app).get(
        "/integrations/v1/zoho/oauth/callback",
        params={"state": "s" * 40, "code": "grant-code"},
    )
    assert response.status_code == 400
    assert response.headers["cache-control"] == "no-store"


def test_oauth_authorize_route_is_admin_only_and_does_not_return_raw_state(monkeypatch):
    started = []
    monkeypatch.setitem(
        app.dependency_overrides,
        require_authenticated_user,
        lambda: {"sub": "admin-sub", "roles": ["company_admin"]},
    )
    monkeypatch.setattr(
        "app.api.integrations.create_authorization_url",
        lambda actor: (started.append(actor) or ("https://accounts.zoho.in/oauth/v2/auth", "private-state")),
    )
    response = TestClient(app).post("/api/integrations/zoho/authorize")
    assert response.status_code == 200
    assert response.json() == {"authorization_url": "https://accounts.zoho.in/oauth/v2/auth"}
    assert started == ["admin-sub"]


def test_oauth_authorize_route_rejects_non_admin_user(monkeypatch):
    monkeypatch.setitem(
        app.dependency_overrides,
        require_authenticated_user,
        lambda: {"sub": "operator-sub", "roles": ["sales_operator"]},
    )
    response = TestClient(app).post("/api/integrations/zoho/authorize")
    assert response.status_code == 403


def test_oauth_disconnect_route_is_admin_only_and_audited(monkeypatch):
    from app.api.deps import get_audit_repo

    recorded = []

    class AuditStub:
        def create(self, event):
            recorded.append(event)

    monkeypatch.setitem(
        app.dependency_overrides,
        require_authenticated_user,
        lambda: {"sub": "admin-sub", "roles": ["company_admin"]},
    )
    monkeypatch.setitem(app.dependency_overrides, get_audit_repo, lambda: AuditStub())
    monkeypatch.setattr("app.api.integrations.disconnect_zoho", lambda: {
        "connection_status": "not_connected", "provider_revocation": "confirmed",
    })
    response = TestClient(app).post("/api/integrations/zoho/disconnect")
    assert response.status_code == 200
    assert recorded[0].action == "zoho_disconnect_requested"
    assert recorded[0].actor == "user:admin-sub"
    assert recorded[0].details == {"provider": "zoho-crm"}


def test_oauth_disconnect_route_rejects_non_admin_user(monkeypatch):
    monkeypatch.setitem(
        app.dependency_overrides,
        require_authenticated_user,
        lambda: {"sub": "operator-sub", "roles": ["sales_operator"]},
    )
    response = TestClient(app).post("/api/integrations/zoho/disconnect")
    assert response.status_code == 403


def test_zoho_mapping_route_is_admin_only_and_audits_configuration(monkeypatch):
    from app.api.deps import get_audit_repo

    recorded = []

    class AuditStub:
        def create(self, event):
            recorded.append(event)

    monkeypatch.setitem(
        app.dependency_overrides,
        require_authenticated_user,
        lambda: {"sub": "admin-sub", "roles": ["company_admin"]},
    )
    monkeypatch.setitem(app.dependency_overrides, get_audit_repo, lambda: AuditStub())
    monkeypatch.setattr("app.api.integrations.update_outcome_field_mapping", lambda enabled, mapping: {
        "connection_status": "configured", "outcome_writeback_enabled": enabled,
        "outcome_field_mapping": mapping,
    })
    response = TestClient(app).put("/api/integrations/zoho/outcome-mapping", json={
        "enabled": True,
        "field_mapping": {"outcome": "Rescue_Outcome"},
    })
    assert response.status_code == 200
    assert response.json()["outcome_writeback_enabled"] is True
    assert recorded[0].action == "zoho_outcome_mapping_update_requested"
    assert recorded[0].details == {"enabled": True, "mapped_fields": ["Rescue_Outcome"]}


def test_zoho_field_metadata_route_rejects_non_admin_user(monkeypatch):
    monkeypatch.setitem(
        app.dependency_overrides,
        require_authenticated_user,
        lambda: {"sub": "operator-sub", "roles": ["sales_operator"]},
    )
    response = TestClient(app).get("/api/integrations/zoho/fields")
    assert response.status_code == 403


def test_oauth_status_route_returns_only_connection_metadata(monkeypatch):
    monkeypatch.setitem(
        app.dependency_overrides,
        require_authenticated_user,
        lambda: {"sub": "admin-sub", "roles": ["company_admin"]},
    )
    monkeypatch.setattr("app.api.integrations.connection_status", lambda: {
        "connection_status": "configured",
        "accounts_region": "accounts.zoho.in",
        "scope": "ZohoCRM.modules.leads.UPDATE",
    })
    response = TestClient(app).get("/api/integrations/zoho/status")
    assert response.status_code == 200
    assert "client_secret" not in response.text
    assert "refresh_token" not in response.text


class _OAuthStateTable:
    def __init__(self):
        self.item = None
        self.status = "OAUTH_PENDING"

    def put_item(self, *, Item, **_kwargs):
        self.item = Item

    def update_item(self, *, ExpressionAttributeValues, **_kwargs):
        if self.status != ExpressionAttributeValues[":pending"]:
            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException", "Message": "already consumed"}},
                "UpdateItem",
            )
        self.status = ExpressionAttributeValues[":processing"]


def test_oauth_state_is_hashed_and_claimed_once(monkeypatch):
    table = _OAuthStateTable()

    class Resource:
        def Table(self, _name):
            return table

    class TestSettings:
        effective_tenant_id = "tenant-test"
        processed_events_table = "events"

    monkeypatch.setattr(zoho_oauth, "settings", TestSettings())
    monkeypatch.setattr(zoho_oauth, "get_boto3_dynamodb_resource", Resource)
    state = "s" * 40

    zoho_oauth._store_oauth_state(state, "admin-sub")

    assert state not in table.item["event_key"]
    assert table.item["expires_at"] > table.item["created_at"]
    assert table.item["requested_by"] == "admin-sub"
    assert zoho_oauth._claim_oauth_state(state) is True
    assert zoho_oauth._claim_oauth_state(state) is False


def test_oauth_token_handler_rejects_redirects_without_forwarding_request_body():
    request = Request("https://accounts.zoho.in/oauth/v2/token", data=b"client_secret=private")
    redirected = zoho_oauth._RejectRedirects().redirect_request(
        request, None, 307, "Temporary Redirect", {}, "https://attacker.example/token"
    )
    assert redirected is None
