"""Server-side Zoho CRM OAuth configuration and token lifecycle helpers."""

import hashlib
import json
import logging
import re
import secrets
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException

from app.config.settings import settings
from app.repositories.base import get_boto3_dynamodb_resource

logger = logging.getLogger(__name__)

ZOHO_ACCOUNTS_URLS = frozenset({
    "https://accounts.zoho.com",
    "https://accounts.zoho.com.au",
    "https://accounts.zoho.eu",
    "https://accounts.zoho.in",
    "https://accounts.zoho.com.cn",
    "https://accounts.zoho.jp",
    "https://accounts.zohocloud.ca",
})
ZOHO_API_DOMAINS = frozenset({
    "https://www.zohoapis.com",
    "https://www.zohoapis.com.au",
    "https://www.zohoapis.eu",
    "https://www.zohoapis.in",
    "https://www.zohoapis.com.cn",
    "https://www.zohoapis.jp",
    "https://www.zohoapis.ca",
    "https://www.zohoapis.sa",
    "https://www.zohoapis.com.sg",
    "https://www.zohoapis.com.mx",
})
ZOHO_FIELD_METADATA_SCOPE = "ZohoCRM.settings.fields.READ"
ZOHO_LEAD_UPDATE_SCOPE = f"ZohoCRM.modules.leads.READ,ZohoCRM.modules.leads.UPDATE,{ZOHO_FIELD_METADATA_SCOPE}"
ZOHO_OUTCOME_RESERVED_FIELDS = frozenset({
    "id", "created_time", "modified_time", "email", "phone", "first_name", "last_name",
    "company", "lead_source", "lead_status", "owner", "is_converted", "converted_date",
})
OAUTH_STATE_TTL_SECONDS = 10 * 60
_access_token: str | None = None
_access_token_expires_at = 0.0
_access_token_api_domain: str | None = None


class ZohoOAuthError(RuntimeError):
    """Safe-to-surface Zoho connection error without provider response details."""


class _RejectRedirects(HTTPRedirectHandler):
    """Never forward OAuth grants or client credentials to a redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _urlopen_no_redirect(request, timeout):
    return build_opener(_RejectRedirects).open(request, timeout=timeout)


def _secret_arn() -> str:
    if not settings.zoho_oauth_secret_arn:
        raise HTTPException(status_code=503, detail="Zoho CRM OAuth is not configured")
    return settings.zoho_oauth_secret_arn


def _secrets_client():
    return boto3.client(
        "secretsmanager",
        region_name=settings.aws_region or None,
        config=Config(connect_timeout=2, read_timeout=4, retries={"total_max_attempts": 2}),
    )


def load_oauth_config() -> dict:
    try:
        raw = _secrets_client().get_secret_value(SecretId=_secret_arn()).get("SecretString", "")
        config = json.loads(raw)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Zoho OAuth configuration could not be loaded (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Zoho CRM OAuth configuration is unavailable") from exc
    if not isinstance(config, dict):
        raise HTTPException(status_code=503, detail="Zoho CRM OAuth configuration is malformed")
    required = ("client_id", "client_secret", "accounts_url", "redirect_uri")
    if any(not isinstance(config.get(key), str) or not config[key].strip() for key in required):
        raise HTTPException(status_code=503, detail="Zoho CRM OAuth configuration is incomplete")
    if config["accounts_url"] not in ZOHO_ACCOUNTS_URLS:
        raise HTTPException(status_code=503, detail="Zoho CRM Accounts region is unsupported")
    redirect = urlsplit(config["redirect_uri"])
    if (
        redirect.scheme != "https"
        or not redirect.hostname
        or redirect.username
        or redirect.password
        or redirect.fragment
    ):
        raise HTTPException(status_code=503, detail="Zoho CRM OAuth redirect URI must be an HTTPS URL")
    api_domain = config.get("api_domain")
    if api_domain is not None and api_domain not in ZOHO_API_DOMAINS:
        raise HTTPException(status_code=503, detail="Zoho CRM API region is unsupported")
    mapping = config.get("outcome_field_mapping")
    if mapping is not None:
        if not isinstance(mapping, dict) or not isinstance(mapping.get("outcome"), str):
            raise HTTPException(status_code=503, detail="Zoho outcome field mapping is malformed")
        allowed_mapping_keys = {"outcome", "sales_value", "sales_currency", "reason", "recorded_at"}
        if set(mapping) - allowed_mapping_keys:
            raise HTTPException(status_code=503, detail="Zoho outcome field mapping contains unsupported fields")
        values = list(mapping.values())
        if (
            any(not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,99}", value) for value in values)
            or len({value.casefold() for value in values if isinstance(value, str)}) != len(values)
            or any(value.casefold() in ZOHO_OUTCOME_RESERVED_FIELDS for value in values if isinstance(value, str))
        ):
            raise HTTPException(status_code=503, detail="Zoho outcome field mapping contains invalid or duplicate field names")
    if "outcome_writeback_enabled" in config and not isinstance(config["outcome_writeback_enabled"], bool):
        raise HTTPException(status_code=503, detail="Zoho outcome writeback setting is malformed")
    if "pending_revocation_token" in config and (
        not isinstance(config["pending_revocation_token"], str) or not config["pending_revocation_token"]
    ):
        raise HTTPException(status_code=503, detail="Zoho pending revocation state is malformed")
    if "requested_scopes" in config and (
        not isinstance(config["requested_scopes"], list)
        or any(not isinstance(scope, str) for scope in config["requested_scopes"])
    ):
        raise HTTPException(status_code=503, detail="Zoho authorization scope state is malformed")
    return config


def save_oauth_config(config: dict) -> None:
    global _access_token, _access_token_expires_at, _access_token_api_domain
    try:
        _secrets_client().put_secret_value(
            SecretId=_secret_arn(),
            SecretString=json.dumps(config, separators=(",", ":")),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Zoho OAuth credentials could not be stored (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Zoho CRM connection could not be stored securely") from exc
    _access_token = None
    _access_token_expires_at = 0.0
    _access_token_api_domain = None


def create_authorization_url(initiated_by: str) -> tuple[str, str]:
    if not isinstance(initiated_by, str) or not initiated_by or len(initiated_by) > 256:
        raise HTTPException(status_code=403, detail="A valid administrator identity is required")
    config = load_oauth_config()
    if config.get("pending_revocation_token"):
        raise HTTPException(status_code=409, detail="Retry Zoho disconnection before connecting another organization")
    state = secrets.token_urlsafe(32)
    authorization_url = f"{config['accounts_url']}/oauth/v2/auth?{urlencode({
        'scope': ZOHO_LEAD_UPDATE_SCOPE,
        'client_id': config['client_id'],
        'response_type': 'code',
        'access_type': 'offline',
        'redirect_uri': config['redirect_uri'],
        'state': state,
    })}"
    _store_oauth_state(state, initiated_by)
    return authorization_url, state


def _state_key(state: str) -> str:
    return f"{settings.effective_tenant_id}#zoho-oauth-state#{hashlib.sha256(state.encode()).hexdigest()}"


def _store_oauth_state(state: str, initiated_by: str) -> None:
    dynamodb = get_boto3_dynamodb_resource()
    if not dynamodb:
        raise HTTPException(status_code=503, detail="Zoho connection state storage is unavailable")
    now = int(time.time())
    item = {
        "event_key": _state_key(state),
        "tenant_id": settings.effective_tenant_id,
        "provider": "zoho-crm",
        "status": "OAUTH_PENDING",
        "requested_by": initiated_by,
        "created_at": now,
        "expires_at": now + OAUTH_STATE_TTL_SECONDS,
    }
    try:
        dynamodb.Table(settings.processed_events_table).put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(event_key)",
        )
    except (ClientError, BotoCoreError) as exc:
        logger.error("Zoho OAuth state could not be stored (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Zoho connection state could not be stored") from exc


def _claim_oauth_state(state: str) -> bool:
    dynamodb = get_boto3_dynamodb_resource()
    if not dynamodb:
        raise HTTPException(status_code=503, detail="Zoho connection state storage is unavailable")
    try:
        dynamodb.Table(settings.processed_events_table).update_item(
            Key={"event_key": _state_key(state)},
            UpdateExpression="SET #status = :processing",
            ConditionExpression=(
                "tenant_id = :tenant AND provider = :provider AND #status = :pending AND expires_at > :now"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":tenant": settings.effective_tenant_id,
                ":provider": "zoho-crm",
                ":pending": "OAUTH_PENDING",
                ":processing": "OAUTH_PROCESSING",
                ":now": int(time.time()),
            },
        )
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        logger.error("Zoho OAuth state could not be claimed (%s)", exc.response.get("Error", {}).get("Code", "ClientError"))
        raise HTTPException(status_code=503, detail="Zoho connection state could not be validated") from exc
    except BotoCoreError as exc:
        logger.error("Zoho OAuth state could not be claimed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Zoho connection state could not be validated") from exc


def _finish_oauth_state(state: str, final_status: str) -> None:
    dynamodb = get_boto3_dynamodb_resource()
    if not dynamodb:
        raise HTTPException(status_code=503, detail="Zoho connection state storage is unavailable")
    try:
        dynamodb.Table(settings.processed_events_table).update_item(
            Key={"event_key": _state_key(state)},
            UpdateExpression="SET #status = :final",
            ConditionExpression="tenant_id = :tenant AND #status = :processing",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":tenant": settings.effective_tenant_id,
                ":processing": "OAUTH_PROCESSING",
                ":final": final_status,
            },
        )
    except (ClientError, BotoCoreError) as exc:
        logger.error("Zoho OAuth state could not be finalized (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Zoho connection state could not be finalized") from exc


def _token_request(accounts_url: str, parameters: dict) -> dict:
    if accounts_url not in ZOHO_ACCOUNTS_URLS:
        raise ZohoOAuthError("Zoho Accounts region is unsupported")
    request = Request(
        f"{accounts_url}/oauth/v2/token",
        data=urlencode(parameters).encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with _urlopen_no_redirect(request, timeout=8) as response:
            result = json.loads(response.read(64 * 1024))
    except HTTPError as exc:
        exc.close()
        raise ZohoOAuthError("Zoho rejected the OAuth token request") from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise ZohoOAuthError("Zoho OAuth token service is unavailable") from exc
    if not isinstance(result, dict) or result.get("error"):
        raise ZohoOAuthError("Zoho rejected the OAuth token request")
    access_token = result.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise ZohoOAuthError("Zoho returned an invalid OAuth token response")
    api_domain = result.get("api_domain")
    if api_domain is not None and api_domain not in ZOHO_API_DOMAINS:
        raise ZohoOAuthError("Zoho returned an unsupported CRM API region")
    return result


def revoke_refresh_token(config: dict, refresh_token: str) -> None:
    """Revoke a Zoho grant using its data-center-specific Accounts endpoint."""
    if config.get("accounts_url") not in ZOHO_ACCOUNTS_URLS or not refresh_token:
        raise ZohoOAuthError("Zoho revocation configuration is invalid")
    request = Request(
        f"{config['accounts_url']}/oauth/v2/token/revoke?{urlencode({'token': refresh_token})}",
        data=b"",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with _urlopen_no_redirect(request, timeout=8) as response:
            body = response.read(16 * 1024)
    except HTTPError as exc:
        exc.close()
        raise ZohoOAuthError("Zoho did not confirm token revocation") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ZohoOAuthError("Zoho token revocation could not be confirmed") from exc
    if body:
        try:
            result = json.loads(body)
        except ValueError as exc:
            raise ZohoOAuthError("Zoho returned an invalid revocation response") from exc
        if not isinstance(result, dict) or result.get("error"):
            raise ZohoOAuthError("Zoho did not confirm token revocation")


def exchange_authorization_code(config: dict, code: str) -> dict:
    return _token_request(config["accounts_url"], {
        "code": code,
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "redirect_uri": config["redirect_uri"],
        "grant_type": "authorization_code",
    })


def refresh_access_token(config: dict | None = None) -> tuple[str, str]:
    """Return an access token and validated API domain, caching only in this process."""
    global _access_token, _access_token_expires_at, _access_token_api_domain
    config = config or load_oauth_config()
    if _access_token and time.monotonic() < _access_token_expires_at and _access_token_api_domain:
        return _access_token, _access_token_api_domain
    refresh_token = config.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise ZohoOAuthError("Zoho CRM is not connected")
    response = _token_request(config["accounts_url"], {
        "refresh_token": refresh_token,
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "grant_type": "refresh_token",
    })
    api_domain = response.get("api_domain") or config.get("api_domain")
    if api_domain not in ZOHO_API_DOMAINS:
        raise ZohoOAuthError("Zoho CRM API region is missing or unsupported")
    expires_in = response.get("expires_in", 3600)
    if isinstance(expires_in, bool) or not isinstance(expires_in, (int, float)) or expires_in < 120:
        raise ZohoOAuthError("Zoho returned an invalid OAuth token lifetime")
    _access_token = response["access_token"]
    _access_token_api_domain = api_domain
    _access_token_expires_at = time.monotonic() + min(expires_in - 60, 3500)
    return _access_token, _access_token_api_domain


def connection_status(config: dict | None = None) -> dict:
    if config is None:
        config = load_oauth_config()
    connected = bool(config.get("refresh_token"))
    pending_revocation = bool(config.get("pending_revocation_token"))
    return {
        "connection_status": "configured" if connected else "revocation_pending" if pending_revocation else "not_connected",
        "connected_at": config.get("connected_at"),
        "accounts_region": urlsplit(config["accounts_url"]).hostname,
        "api_region": urlsplit(config["api_domain"]).hostname if config.get("api_domain") else None,
        "scope": ZOHO_LEAD_UPDATE_SCOPE,
        "outcome_writeback_enabled": bool(connected and config.get("outcome_writeback_enabled") and config.get("outcome_field_mapping")),
        "outcome_field_mapping": config.get("outcome_field_mapping") if isinstance(config.get("outcome_field_mapping"), dict) else {},
        "field_metadata_scope_requested": ZOHO_FIELD_METADATA_SCOPE in config.get("requested_scopes", []),
    }


def list_writable_lead_fields(config: dict | None = None) -> list[dict]:
    """Return safe, writable custom Leads fields with supported mapping roles."""
    config = config or load_oauth_config()
    if not config.get("refresh_token"):
        raise HTTPException(status_code=409, detail="Connect Zoho CRM before configuring outcome fields")
    if ZOHO_FIELD_METADATA_SCOPE not in config.get("requested_scopes", []):
        raise HTTPException(status_code=409, detail="Reconnect Zoho to grant read-only access to Leads field metadata")
    access_token, api_domain = refresh_access_token(config)
    request = Request(
        f"{api_domain}/crm/v8/settings/fields?{urlencode({'module': 'Leads', 'type': 'all'})}",
        headers={"Authorization": f"Zoho-oauthtoken {access_token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with _urlopen_no_redirect(request, timeout=8) as response:
            payload = json.loads(response.read(1024 * 1024))
    except HTTPError as exc:
        code = exc.code
        exc.close()
        if code in {401, 403}:
            raise HTTPException(status_code=409, detail="Zoho denied field metadata access; reconnect and check the CRM user's field permissions") from exc
        raise HTTPException(status_code=503, detail="Zoho field metadata is temporarily unavailable") from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Zoho field metadata is temporarily unavailable") from exc
    records = payload.get("fields") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise HTTPException(status_code=503, detail="Zoho returned invalid field metadata")

    allowed_types = {
        "outcome": {"text", "textarea", "picklist"},
        "sales_value": {"currency", "integer", "bigint", "decimal", "double"},
        "sales_currency": {"text"},
        "reason": {"text", "textarea"},
        "recorded_at": {"datetime"},
    }
    result = []
    for field in records:
        if not isinstance(field, dict):
            continue
        api_name = field.get("api_name")
        data_type = field.get("data_type")
        operations = field.get("operation_type")
        private = field.get("private")
        if (
            not isinstance(api_name, str)
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,99}", api_name)
            or api_name.casefold() in ZOHO_OUTCOME_RESERVED_FIELDS
            or field.get("custom_field") is not True
            or not isinstance(operations, dict)
            or operations.get("api_update") is not True
            or field.get("read_only") is True
            or field.get("field_read_only") is True
            or field.get("system_mandatory") is True
            or (isinstance(private, dict) and private.get("restricted") is True)
            or not isinstance(data_type, str)
        ):
            continue
        roles = [role for role, types in allowed_types.items() if data_type.casefold() in types]
        pick_values = field.get("pick_list_values")
        actual_values = {
            value
            for item in pick_values if isinstance(item, dict)
            for value in [item.get("actual_value", item.get("display_value"))]
            if isinstance(value, str) and item.get("type") != "unused"
        } if isinstance(pick_values, list) else set()
        if "outcome" in roles and data_type.casefold() == "picklist" and not {"won", "lost", "disqualified"}.issubset(actual_values):
            roles.remove("outcome")
        if not roles:
            continue
        result.append({
            "api_name": api_name,
            "label": field.get("field_label") or field.get("display_label") or api_name,
            "data_type": data_type,
            "eligible_for": roles,
            "pick_list_values": sorted(value for value in actual_values if isinstance(value, str)) if "outcome" in roles and isinstance(pick_values, list) else [],
        })
    return result


def update_outcome_field_mapping(enabled: bool, field_mapping: dict | None = None) -> dict:
    config = load_oauth_config()
    if not config.get("refresh_token"):
        raise HTTPException(status_code=409, detail="Connect Zoho CRM before configuring outcome writeback")
    if not enabled:
        config["outcome_writeback_enabled"] = False
        save_oauth_config(config)
        return connection_status(config)
    mapping = field_mapping if field_mapping is not None else config.get("outcome_field_mapping")
    allowed_keys = {"outcome", "sales_value", "sales_currency", "reason", "recorded_at"}
    if (
        not isinstance(mapping, dict)
        or not isinstance(mapping.get("outcome"), str)
        or set(mapping) - allowed_keys
        or any(not isinstance(value, str) for value in mapping.values())
        or len({value.casefold() for value in mapping.values()}) != len(mapping)
    ):
        raise HTTPException(status_code=422, detail="Choose one distinct Zoho field for each configured outcome value")
    fields = {field["api_name"]: field for field in list_writable_lead_fields(config)}
    invalid = [
        role for role, api_name in mapping.items()
        if api_name not in fields or role not in fields[api_name]["eligible_for"]
    ]
    if invalid:
        raise HTTPException(status_code=422, detail="One or more selected Zoho fields are not writable or have an incompatible type")
    config["outcome_field_mapping"] = mapping
    config["outcome_writeback_enabled"] = True
    save_oauth_config(config)
    return connection_status(config)


def disconnect_zoho() -> dict:
    """Disable local CRM access first and retain a retryable token until revocation is confirmed."""
    config = load_oauth_config()
    token = config.get("pending_revocation_token") or config.get("refresh_token")
    if not token:
        return {"connection_status": "not_connected", "provider_revocation": "not_required"}
    config["pending_revocation_token"] = token
    config.pop("refresh_token", None)
    config.pop("connected_at", None)
    config.pop("api_domain", None)
    config["outcome_writeback_enabled"] = False
    save_oauth_config(config)
    try:
        revoke_refresh_token(config, token)
    except ZohoOAuthError as exc:
        logger.warning("Zoho revocation pending after local disconnect (%s)", type(exc).__name__)
        return {"connection_status": "revocation_pending", "provider_revocation": "pending"}
    config.pop("pending_revocation_token", None)
    save_oauth_config(config)
    return {"connection_status": "not_connected", "provider_revocation": "confirmed"}


def connect_with_authorization_code(state: str, code: str) -> None:
    if not isinstance(state, str) or len(state) < 32 or len(state) > 256:
        raise HTTPException(status_code=400, detail="Zoho authorization state is invalid")
    if not isinstance(code, str) or not code or len(code) > 4096:
        raise HTTPException(status_code=400, detail="Zoho authorization code is invalid")
    if not _claim_oauth_state(state):
        raise HTTPException(status_code=400, detail="Zoho authorization state is expired or already used")
    try:
        config = load_oauth_config()
        response = exchange_authorization_code(config, code)
        refresh_token = response.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise ZohoOAuthError("Zoho did not issue a refresh token")
        api_domain = response.get("api_domain")
        if api_domain not in ZOHO_API_DOMAINS:
            raise ZohoOAuthError("Zoho did not return a supported CRM API region")
        config["refresh_token"] = refresh_token
        config["api_domain"] = api_domain
        config["connected_at"] = datetime.now(timezone.utc).isoformat()
        config["requested_scopes"] = ZOHO_LEAD_UPDATE_SCOPE.split(",")
        save_oauth_config(config)
    except Exception:
        _finish_oauth_state(state, "OAUTH_FAILED")
        raise
    _finish_oauth_state(state, "OAUTH_CONNECTED")


def mark_authorization_denied(state: str) -> None:
    if not isinstance(state, str) or len(state) < 32 or len(state) > 256:
        raise HTTPException(status_code=400, detail="Zoho authorization state is invalid")
    if not _claim_oauth_state(state):
        raise HTTPException(status_code=400, detail="Zoho authorization state is expired or already used")
    _finish_oauth_state(state, "OAUTH_DENIED")
