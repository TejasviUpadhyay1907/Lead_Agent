"""Conflict-aware, narrow Zoho CRM outcome updates."""

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request

from app.integrations.zoho_oauth import (
    ZOHO_API_DOMAINS,
    ZOHO_OUTCOME_RESERVED_FIELDS,
    ZohoOAuthError,
    _urlopen_no_redirect,
    load_oauth_config,
    refresh_access_token,
)

logger = logging.getLogger(__name__)


class ZohoWritebackError(RuntimeError):
    """Provider error classified for safe retry behavior."""

    def __init__(self, code: str, *, retryable: bool):
        super().__init__(code)
        self.code = code
        self.retryable = retryable


def build_outcome_fields(config: dict, outcome: dict) -> dict:
    mapping = config.get("outcome_field_mapping")
    if not config.get("outcome_writeback_enabled") or not isinstance(mapping, dict):
        raise ZohoWritebackError("writeback_not_configured", retryable=False)
    fields = {mapping["outcome"]: outcome["outcome"]}
    for source, target in mapping.items():
        if source == "outcome":
            continue
        # Send null for an intentionally absent mapped value so corrections do
        # not leave a stale amount, currency, or reason in the CRM record.
        fields[target] = outcome.get(source)
    return fields


def _request_json(url: str, access_token: str, method: str, payload: dict | None = None, modified_since: str | None = None) -> dict:
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}", "Accept": "application/json"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if modified_since:
        headers["If-Unmodified-Since"] = modified_since
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with _urlopen_no_redirect(request, timeout=8) as response:
            raw = response.read(256 * 1024)
        value = json.loads(raw)
    except HTTPError as exc:
        code = exc.code
        exc.close()
        if code == 412:
            raise ZohoWritebackError("crm_record_changed", retryable=False) from exc
        if code in {408, 425, 429} or code >= 500:
            raise ZohoWritebackError("provider_temporary_error", retryable=True) from exc
        if code in {401, 403}:
            raise ZohoWritebackError("provider_authorization_failed", retryable=False) from exc
        raise ZohoWritebackError("provider_rejected_update", retryable=False) from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise ZohoWritebackError("provider_unavailable", retryable=True) from exc
    if not isinstance(value, dict):
        raise ZohoWritebackError("invalid_provider_response", retryable=True)
    return value


def update_lead_outcome(record_id: str, fields: dict) -> None:
    config = load_oauth_config()
    if not config.get("refresh_token"):
        raise ZohoOAuthError("Zoho CRM is not connected")
    mapping = config.get("outcome_field_mapping")
    if (
        not config.get("outcome_writeback_enabled")
        or not isinstance(mapping, dict)
        or not mapping
        or not set(fields).issubset(set(mapping.values()))
        or any(str(field).casefold() in ZOHO_OUTCOME_RESERVED_FIELDS for field in fields)
    ):
        raise ZohoWritebackError("field_mapping_changed", retryable=False)
    access_token, api_domain = refresh_access_token(config)
    if api_domain not in ZOHO_API_DOMAINS:
        raise ZohoWritebackError("unsupported_api_region", retryable=False)
    record_url = f"{api_domain}/crm/v8/Leads/{quote(record_id, safe='')}"
    current = _request_json(record_url, access_token, "GET")
    records = current.get("data")
    if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
        raise ZohoWritebackError("crm_record_not_found", retryable=False)
    modified_time = records[0].get("Modified_Time")
    if not isinstance(modified_time, str) or not modified_time:
        raise ZohoWritebackError("crm_version_missing", retryable=False)
    result = _request_json(
        f"{api_domain}/crm/v8/Leads",
        access_token,
        "PUT",
        {"data": [{"id": record_id, **fields}]},
        modified_since=modified_time,
    )
    details = result.get("data")
    if not isinstance(details, list) or len(details) != 1 or details[0].get("code") != "SUCCESS":
        raise ZohoWritebackError("provider_rejected_update", retryable=False)
