"""
LeadRescue AI — Business Configuration Model
Pydantic model for dynamic business configuration (e.g. response_target_minutes, scoring rules).
"""

from datetime import datetime, timezone
import json
import math
import re
from decimal import Decimal
from typing import Any, Dict
from pydantic import BaseModel, ConfigDict, Field, field_validator


_SENSITIVE_KEY = re.compile(r"(secret|token|password|passwd|credential|api[_-]?key|private)", re.IGNORECASE)
REDACTED_VALUE = "[redacted]"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_business_rules(value: Dict[str, Any]) -> Dict[str, Any]:
    """Validate policy inputs and bound extensible JSON before persistence/use."""
    if not isinstance(value, dict):
        raise ValueError("config_value must be an object")

    def normalize_json(item):
        if isinstance(item, Decimal):
            if not item.is_finite():
                raise ValueError("config_value must contain finite numbers only")
            try:
                item = int(item) if item == item.to_integral_value() else float(item)
            except (OverflowError, ValueError) as exc:
                raise ValueError("config_value numbers must fit DynamoDB's supported range") from exc
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("config_value must contain finite numbers only")
        if type(item) is int and len(str(abs(item))) > 38:
            raise ValueError("config_value numbers must fit DynamoDB's 38-digit precision")
        if isinstance(item, float) and item != 0 and not 1e-130 <= abs(item) <= 1e125:
            raise ValueError("config_value numbers must fit DynamoDB's supported range")
        if isinstance(item, dict):
            if not all(isinstance(key, str) for key in item):
                raise ValueError("config_value object keys must be strings")
            return {key: normalize_json(child) for key, child in item.items()}
        if isinstance(item, list):
            return [normalize_json(child) for child in item]
        if item is None or isinstance(item, (str, bool, int, float)):
            return item
        raise ValueError("config_value must contain JSON-compatible values only")

    value = normalize_json(value)
    try:
        encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("config_value must contain finite JSON values only") from exc
    if len(encoded.encode("utf-8")) > 64_000:
        raise ValueError("config_value must not exceed 64 KB")

    normalized = dict(value)
    if "business_name" in normalized:
        name = normalized["business_name"]
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
            raise ValueError("business_name must contain 1 to 120 non-space characters")
        normalized["business_name"] = name.strip()

    if "response_target_minutes" in normalized:
        minutes = normalized["response_target_minutes"]
        if type(minutes) is not int or not 1 <= minutes <= 10_080:
            raise ValueError("response_target_minutes must be an integer from 1 to 10080")

    if "high_value_threshold" in normalized:
        threshold = normalized["high_value_threshold"]
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise ValueError("high_value_threshold must be a non-negative number")
        if not math.isfinite(threshold) or threshold < 0 or threshold > 1_000_000_000_000_000:
            raise ValueError("high_value_threshold must be between 0 and 1000000000000000")

    if "supported_locations" in normalized:
        locations = normalized["supported_locations"]
        if not isinstance(locations, list) or len(locations) > 200:
            raise ValueError("supported_locations must be a list of at most 200 locations")
        cleaned = []
        seen = set()
        for location in locations:
            if not isinstance(location, str) or not 1 <= len(location.strip()) <= 120:
                raise ValueError("Each supported location must contain 1 to 120 non-space characters")
            location = location.strip()
            if location.casefold() in seen:
                raise ValueError("supported_locations must not contain duplicates")
            seen.add(location.casefold())
            cleaned.append(location)
        normalized["supported_locations"] = cleaned

    return normalized


def reject_secret_like_keys(value: Any) -> None:
    """Keep credentials out of editable business rules; use a secret store instead."""
    if isinstance(value, dict):
        for key, child in value.items():
            if _SENSITIVE_KEY.search(key) and child != REDACTED_VALUE:
                raise ValueError("Credential-like settings must be stored in a secret manager, not business rules")
            reject_secret_like_keys(child)
    elif isinstance(value, list):
        for child in value:
            reject_secret_like_keys(child)


def redact_sensitive_config(value: Any) -> Any:
    """Recursively mask credential-like keys before returning settings to a client."""
    if isinstance(value, dict):
        return {
            key: REDACTED_VALUE if _SENSITIVE_KEY.search(key) else redact_sensitive_config(child)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_config(child) for child in value]
    return value


def restore_redacted_config(submitted: Any, existing: Any) -> Any:
    """Preserve legacy masked values when the settings form saves other fields."""
    if isinstance(submitted, dict):
        existing = existing if isinstance(existing, dict) else {}
        restored = {}
        for key, child in submitted.items():
            if _SENSITIVE_KEY.search(key) and child == REDACTED_VALUE and key in existing:
                restored[key] = existing[key]
            else:
                restored[key] = restore_redacted_config(child, existing.get(key))
        return restored
    if isinstance(submitted, list):
        existing = existing if isinstance(existing, list) else []
        return [restore_redacted_config(child, existing[index] if index < len(existing) else None) for index, child in enumerate(submitted)]
    return submitted


class ConfigUpdate(BaseModel):
    config_value: Dict[str, Any]
    model_config = ConfigDict(extra="forbid")

    @field_validator("config_value")
    @classmethod
    def validate_config_value(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        normalized = validate_business_rules(value)
        reject_secret_like_keys(normalized)
        return normalized


class ConfigModel(BaseModel):
    config_key: str
    config_value: Dict[str, Any]
    updated_at: str = Field(default_factory=utc_now_iso)

    model_config = ConfigDict(extra="ignore", from_attributes=True)

    @field_validator("config_value")
    @classmethod
    def validate_config_value(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        return validate_business_rules(value)
