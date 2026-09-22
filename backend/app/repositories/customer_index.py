"""Deterministic pseudonymous DynamoDB partition keys for customer history."""

import hashlib
import re
from typing import Optional


def _key(tenant_id: str, kind: str, value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    normalized = value.strip().lower() if kind == "email" else re.sub(r"\D", "", value)
    if not normalized:
        return None
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"{tenant_id}#{digest}"


def customer_index_keys(tenant_id: str, email: Optional[str], phone: Optional[str]) -> dict:
    return {
        "tenant_email_key": _key(tenant_id, "email", email),
        "tenant_phone_key": _key(tenant_id, "phone", phone),
    }
