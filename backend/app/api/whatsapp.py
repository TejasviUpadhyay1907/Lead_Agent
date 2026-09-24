"""Authenticated, non-secret provider configuration preview for operators."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.security import require_roles
from app.config.settings import settings
from app.integrations.whatsapp import WhatsAppConfigurationError, load_config, template_fingerprint

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])


class WhatsAppConfigurationView(BaseModel):
    configured: bool
    outbound_enabled: bool
    template_name: Optional[str] = None
    template_language: Optional[str] = None
    template_body: Optional[str] = None
    template_fingerprint: Optional[str] = None


@router.get("/configuration", response_model=WhatsAppConfigurationView)
def get_whatsapp_configuration(_operator=Depends(require_roles(settings.operator_role, settings.admin_role))):
    if not settings.whatsapp_secret_arn:
        return WhatsAppConfigurationView(configured=False, outbound_enabled=False)
    try:
        config = load_config()
    except WhatsAppConfigurationError as exc:
        raise HTTPException(status_code=503, detail="WhatsApp provider configuration is unavailable") from exc
    return WhatsAppConfigurationView(
        configured=True,
        outbound_enabled=settings.whatsapp_send_enabled,
        template_name=config.template_name,
        template_language=config.template_language,
        template_body=config.template_body,
        template_fingerprint=template_fingerprint(config),
    )
