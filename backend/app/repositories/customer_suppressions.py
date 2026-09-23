"""Tenant-scoped contact suppression keys for durable opt-out enforcement."""

from datetime import datetime, timezone
from typing import Optional

from app.repositories.customer_index import customer_index_keys

MIGRATION_MARKER_PREFIX = "migration-complete#"
HISTORY_INDEX_MARKER_PREFIX = "history-index-complete#"


def migration_marker_key(tenant_id: str) -> str:
    return f"{MIGRATION_MARKER_PREFIX}{tenant_id}"


def history_index_marker_key(tenant_id: str) -> str:
    return f"{HISTORY_INDEX_MARKER_PREFIX}{tenant_id}"


def suppression_keys(
    tenant_id: str,
    email: Optional[str],
    phone: Optional[str],
    *,
    hmac_key: bytes | None = None,
) -> list[str]:
    """Return keyed, type-separated pseudonyms for the contact identifiers."""
    indexed = customer_index_keys(tenant_id, email, phone, hmac_key=hmac_key)
    return [
        value
        for value in (
            f"email#{indexed['tenant_email_key']}" if indexed["tenant_email_key"] else None,
            f"phone#{indexed['tenant_phone_key']}" if indexed["tenant_phone_key"] else None,
        )
        if value
    ]


def suppression_items(
    tenant_id: str,
    lead_id: str,
    email: Optional[str],
    phone: Optional[str],
    *,
    hmac_key: bytes | None = None,
) -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "suppression_key": key,
            "tenant_id": tenant_id,
            "lead_id": lead_id,
            "reason": "customer_opt_out",
            "suppressed_at": now,
        }
        for key in suppression_keys(tenant_id, email, phone, hmac_key=hmac_key)
        if key
    ]
