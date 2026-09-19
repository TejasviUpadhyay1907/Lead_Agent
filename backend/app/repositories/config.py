"""
LeadRescue AI — Config Repository
Provides persistence for Business Configuration (DynamoDB & Memory fallback).
"""

from typing import Dict, Optional
from app.config.settings import settings
from app.models.config import ConfigModel, ConfigUpdate
from app.repositories.base import get_boto3_dynamodb_resource

DEFAULT_BUSINESS_CONFIG = {
    "config_key": "business_rules",
    "config_value": {
        "response_target_minutes": 20,
        "high_value_threshold": 50000,
        "business_name": "Precision Engineering Solutions",
        "supported_locations": ["Pune", "Mumbai", "Bengaluru", "Delhi"],
    },
}


class ConfigRepository:
    def __init__(self, use_memory: bool = False):
        self.use_memory = use_memory
        self._memory_store: Dict[str, ConfigModel] = {}
        self._table = None

        if not use_memory:
            dynamodb = get_boto3_dynamodb_resource()
            if dynamodb and settings.config_table:
                try:
                    self._table = dynamodb.Table(settings.config_table)
                except Exception:
                    self.use_memory = True
            else:
                self.use_memory = True

        # Initialize default config in memory store
        default_item = ConfigModel(**DEFAULT_BUSINESS_CONFIG)
        self._memory_store[default_item.config_key] = default_item

    def get_config(self, key: str = "business_rules") -> ConfigModel:
        if self.use_memory or not self._table:
            return self._memory_store.get(key, ConfigModel(**DEFAULT_BUSINESS_CONFIG))
        try:
            response = self._table.get_item(Key={"config_key": key})
            item = response.get("Item")
            if item:
                return ConfigModel(**item)
            return self._memory_store.get(key, ConfigModel(**DEFAULT_BUSINESS_CONFIG))
        except Exception:
            return self._memory_store.get(key, ConfigModel(**DEFAULT_BUSINESS_CONFIG))

    def update_config(self, key: str, config_update: ConfigUpdate) -> ConfigModel:
        current = self.get_config(key)
        current.config_value.update(config_update.config_value)

        if self.use_memory or not self._table:
            self._memory_store[key] = current
            return current

        try:
            self._table.put_item(Item=current.model_dump())
            return current
        except Exception:
            self._memory_store[key] = current
            return current
