"""
LeadRescue AI — Config API Endpoints
Endpoints for viewing and updating business configuration.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_audit_repo, get_config_repo
from app.models.audit import AuditEventCreate
from app.repositories.audit import AuditRepository
from app.models.config import ConfigModel, ConfigUpdate, redact_sensitive_config, restore_redacted_config
from app.repositories.config import ConcurrentConfigUpdateError, ConfigRepository
from app.api.security import require_roles
from app.config.settings import settings

router = APIRouter(prefix="/config", tags=["Config"])


def _public_config(config: ConfigModel) -> ConfigModel:
    return config.model_copy(update={"config_value": redact_sensitive_config(config.config_value)})


@router.get("", response_model=ConfigModel)
def get_config(
    _operator=Depends(require_roles(settings.operator_role, settings.admin_role)),
    config_repo: ConfigRepository = Depends(get_config_repo),
):
    """
    Get current business configuration rules.
    """
    return _public_config(config_repo.get_config("business_rules"))


@router.put("", response_model=ConfigModel)
def update_config(
    config_update: ConfigUpdate,
    _admin=Depends(require_roles(settings.admin_role)),
    config_repo: ConfigRepository = Depends(get_config_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
):
    """
    Update business configuration rules.
    """
    audit = audit_repo.build(
        AuditEventCreate(
            lead_id="system",
            action="business_config_updated",
            actor=f"user:{_admin['sub']}",
            details={"updated_keys": sorted(config_update.config_value.keys())},
        )
    )
    existing = config_repo.get_config("business_rules")
    safe_update = config_update.model_copy(
        update={"config_value": restore_redacted_config(config_update.config_value, existing.config_value)}
    )
    try:
        updated = config_repo.update_config_with_audit("business_rules", safe_update, audit, audit_repo)
        return _public_config(updated)
    except ConcurrentConfigUpdateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Company rules were changed by another administrator. Reload settings before saving again.",
        ) from exc
