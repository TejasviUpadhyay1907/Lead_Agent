"""Company administrator controls for connected CRM integrations."""

from fastapi import APIRouter, Depends

from app.api.deps import get_audit_repo
from app.api.security import require_roles
from app.config.settings import settings
from app.integrations.zoho_oauth import connection_status, create_authorization_url, disconnect_zoho
from app.models.audit import AuditEventCreate
from app.repositories.audit import AuditRepository

router = APIRouter(prefix="/integrations", tags=["Integrations"])


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
