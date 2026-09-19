"""
LeadRescue AI — Business Configuration Model
Pydantic model for dynamic business configuration (e.g. response_target_minutes, scoring rules).
"""

from datetime import datetime, timezone
from typing import Any, Dict
from pydantic import BaseModel, ConfigDict, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConfigUpdate(BaseModel):
    config_value: Dict[str, Any]
    model_config = ConfigDict(extra="forbid")


class ConfigModel(BaseModel):
    config_key: str
    config_value: Dict[str, Any]
    updated_at: str = Field(default_factory=utc_now_iso)

    model_config = ConfigDict(extra="ignore", from_attributes=True)
