"""Company administrator controls for connected CRM integrations."""

from fastapi import APIRouter, Depends

from app.api.security import require_roles
from app.config.settings import settings
from app.integrations.zoho_oauth import connection_status, create_authorization_url

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
