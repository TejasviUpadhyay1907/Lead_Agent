"""Server-side Zoho CRM OAuth configuration and token lifecycle helpers."""

import hashlib
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

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
ZOHO_LEAD_UPDATE_SCOPE = "ZohoCRM.modules.leads.UPDATE"
OAUTH_STATE_TTL_SECONDS = 10 * 60
_access_token: str | None = None
_access_token_expires_at = 0.0
_access_token_api_domain: str | None = None


class ZohoOAuthError(RuntimeError):
    """Safe-to-surface Zoho connection error without provider response details."""


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
        with urlopen(request, timeout=8) as response:
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


def connection_status() -> dict:
    config = load_oauth_config()
    return {
        "connection_status": "configured" if config.get("refresh_token") else "not_connected",
        "connected_at": config.get("connected_at"),
        "accounts_region": urlsplit(config["accounts_url"]).hostname,
        "api_region": urlsplit(config["api_domain"]).hostname if config.get("api_domain") else None,
        "scope": ZOHO_LEAD_UPDATE_SCOPE,
    }


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
