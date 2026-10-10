"""Company administrator controls for connected CRM integrations."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, StringConstraints

from app.api.deps import get_audit_repo
from app.api.security import require_roles
from app.config.settings import settings
from app.integrations.zoho_oauth import (
    connection_status,
    create_authorization_url,
    disconnect_zoho,
    list_writable_lead_fields,
    update_outcome_field_mapping,
)
from app.models.audit import AuditEventCreate
from app.repositories.audit import AuditRepository

router = APIRouter(prefix="/integrations", tags=["Integrations"])
ZohoFieldName = Annotated[
    StrictStr,
    StringConstraints(min_length=1, max_length=100, pattern=r"^[A-Za-z][A-Za-z0-9_]{0,99}$"),
]


class ZohoOutcomeMappingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True
    field_mapping: dict[ZohoFieldName, ZohoFieldName] | None = Field(default=None, max_length=5)


@router.get("/zoho/status")
def get_zoho_connection_status(
    _admin=Depends(require_roles(settings.admin_role)),
):
    """Return safe connection metadata without revealing Zoho credentials."""
    return connection_status()


@router.post("/zoho/authorize")
def authorize_zoho_connection(
    admin=Depends(require_roles(settings.admin_role)),
):
    """Create a short-lived, single-use Zoho OAuth authorization URL."""
    authorization_url, _state = create_authorization_url(admin.get("sub", ""))
    return {"authorization_url": authorization_url}


@router.post("/zoho/disconnect")
def disconnect_zoho_connection(
    admin=Depends(require_roles(settings.admin_role)),
    audit_repo: AuditRepository = Depends(get_audit_repo),
):
    """Disable local Zoho access and attempt remote token revocation."""
    audit_repo.create(AuditEventCreate(
        lead_id="system",
        action="zoho_disconnect_requested",
        actor=f"user:{admin['sub']}",
        details={"provider": "zoho-crm"},
    ))
    return disconnect_zoho()


@router.get("/zoho/fields")
def get_zoho_writable_lead_fields(
    _admin=Depends(require_roles(settings.admin_role)),
):
    """Return only compatible, writable custom Lead fields for admin mapping."""
    return {"fields": list_writable_lead_fields()}


@router.put("/zoho/outcome-mapping")
def save_zoho_outcome_mapping(
    update: ZohoOutcomeMappingUpdate,
    admin=Depends(require_roles(settings.admin_role)),
    audit_repo: AuditRepository = Depends(get_audit_repo),
):
    """Validate and store the mapped Zoho fields in Secrets Manager."""
    mapping = update.field_mapping or {}
    audit_repo.create(AuditEventCreate(
        lead_id="system",
        action="zoho_outcome_mapping_update_requested",
        actor=f"user:{admin['sub']}",
        details={"enabled": update.enabled, "mapped_fields": sorted(mapping.values())},
    ))
    return update_outcome_field_mapping(update.enabled, update.field_mapping)
