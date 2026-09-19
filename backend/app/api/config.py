"""
LeadRescue AI — Config API Endpoints
Endpoints for viewing and updating business configuration.
"""

from fastapi import APIRouter, Depends

from app.api.deps import get_config_repo
from app.models.config import ConfigModel, ConfigUpdate
from app.repositories.config import ConfigRepository

router = APIRouter(prefix="/config", tags=["Config"])


@router.get("", response_model=ConfigModel)
async def get_config(
    config_repo: ConfigRepository = Depends(get_config_repo),
):
    """
    Get current business configuration rules.
    """
    return config_repo.get_config("business_rules")


@router.put("", response_model=ConfigModel)
async def update_config(
    config_update: ConfigUpdate,
    config_repo: ConfigRepository = Depends(get_config_repo),
):
    """
    Update business configuration rules.
    """
    return config_repo.update_config("business_rules", config_update)
