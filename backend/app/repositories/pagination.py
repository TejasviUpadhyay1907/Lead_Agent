"""Opaque, filter-bound cursors for bounded repository pages."""

import base64
import json
from typing import Any, Dict, Optional


def encode_cursor(state: Dict[str, Any]) -> str:
    payload = json.dumps(state, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_cursor(
    cursor: Optional[str],
    expected_filter: Dict[str, Any],
    key_fields: set[str],
) -> Dict[str, Any]:
    if not cursor:
        return {}
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        state = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if state.get("filter") != expected_filter:
            raise ValueError("Cursor does not match the requested filters")
        offset = state.get("offset")
        last_key = state.get("last_key")
        if offset is not None and (type(offset) is not int or offset < 0):
            raise ValueError("Invalid page offset")
        if last_key is not None and (not isinstance(last_key, dict) or not set(last_key).issubset(key_fields)):
            raise ValueError("Invalid continuation key")
        return state
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Invalid page cursor") from exc
