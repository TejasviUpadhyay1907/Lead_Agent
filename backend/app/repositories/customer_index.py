"""Keyed pseudonymous DynamoDB partition keys for customer identity lookups."""

import hashlib
import hmac
import json
import re
from functools import lru_cache
from typing import Optional

from app.config.settings import settings


_DEMO_INDEX_KEY = b"leadrescue-demo-only-index-key-not-for-production"


class CustomerIndexKeyUnavailableError(RuntimeError):
    """Raised when customer identity keys cannot be derived safely."""


def load_index_hmac_key(secret_arn: str, region: str | None = None) -> bytes:
    """Load a deployment-scoped HMAC key; secret contents are never logged."""
    import boto3
    from botocore.config import Config

    if not secret_arn.strip():
        raise CustomerIndexKeyUnavailableError("Customer index HMAC secret is not configured")
    try:
        response = boto3.client(
            "secretsmanager",
            region_name=region,
            config=Config(connect_timeout=2, read_timeout=3, retries={"total_max_attempts": 2}),
        ).get_secret_value(SecretId=secret_arn)
    except Exception as exc:
        raise CustomerIndexKeyUnavailableError("Customer index HMAC secret could not be loaded") from exc
    secret = response.get("SecretString")
    if not isinstance(secret, str):
        raise CustomerIndexKeyUnavailableError("Customer index HMAC secret must be stored as a Secrets Manager string")
    try:
        parsed = json.loads(secret)
    except json.JSONDecodeError:
        key_text = secret
    else:
        if not isinstance(parsed, dict) or not isinstance(parsed.get("hmac_key"), str):
            raise CustomerIndexKeyUnavailableError("JSON customer index secret must contain a string 'hmac_key' field")
        key_text = parsed["hmac_key"]
    key = key_text.encode("utf-8")
    if len(key) < 32:
        raise CustomerIndexKeyUnavailableError("Customer index HMAC key must contain at least 32 UTF-8 bytes")
    return key


@lru_cache(maxsize=8)
def _cached_index_hmac_key(secret_arn: str, region: str) -> bytes:
    return load_index_hmac_key(secret_arn, region or None)


def _get_index_hmac_key() -> bytes:
    if settings.demo_enabled:
        return _DEMO_INDEX_KEY
    if not settings.customer_index_secret_arn:
        raise CustomerIndexKeyUnavailableError("Customer index HMAC secret is not configured")
    return _cached_index_hmac_key(settings.customer_index_secret_arn, settings.aws_region)


def index_hmac_key_id(key: bytes) -> str:
    """Return a short, non-secret fingerprint for detecting mismatched migrations."""
    return hashlib.sha256(key).hexdigest()[:16]


def require_customer_index_key() -> str:
    """Return a non-secret key fingerprint for migration/readiness comparisons."""
    return index_hmac_key_id(_get_index_hmac_key())


def _normalize(kind: str, value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    normalized = value.strip().lower() if kind == "email" else re.sub(r"\D", "", value)
    return normalized or None


def _key(tenant_id: str, kind: str, normalized: Optional[str], hmac_key: bytes) -> Optional[str]:
    if not normalized:
        return None
    key_id = index_hmac_key_id(hmac_key)
    message = f"leadrescue-index-v1\0{key_id}\0{tenant_id}\0{kind}\0{normalized}".encode("utf-8")
    digest = hmac.new(hmac_key, message, hashlib.sha256).hexdigest()
    return f"{tenant_id}#{key_id}#{digest}"


def customer_index_keys(
    tenant_id: str,
    email: Optional[str],
    phone: Optional[str],
    *,
    hmac_key: bytes | None = None,
) -> dict:
    normalized_email = _normalize("email", email)
    normalized_phone = _normalize("phone", phone)
    key = hmac_key
    if key is None and (normalized_email or normalized_phone):
        key = _get_index_hmac_key()
    if key is not None and len(key) < 32:
        raise CustomerIndexKeyUnavailableError("Customer index HMAC key must contain at least 32 bytes")
    return {
        "tenant_email_key": _key(tenant_id, "email", normalized_email, key) if key else None,
        "tenant_phone_key": _key(tenant_id, "phone", normalized_phone, key) if key else None,
    }
