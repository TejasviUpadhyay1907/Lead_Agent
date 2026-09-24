"""Meta WhatsApp Cloud API client with fixed host and bounded request time."""

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import boto3
from botocore.config import Config

from app.config.settings import settings


class WhatsAppConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class WhatsAppConfig:
    access_token: str
    phone_number_id: str
    app_secret: str
    verify_token: str
    api_version: str
    template_name: str
    template_language: str
    template_body: str


@dataclass(frozen=True)
class WhatsAppSendResult:
    outcome: str  # accepted, failed, unknown
    provider_message_id: Optional[str] = None
    error_code: Optional[str] = None


def template_fingerprint(config: WhatsAppConfig) -> str:
    """Bind send-time operator confirmation to the exact template/account/version preview."""
    parts = (config.phone_number_id, config.api_version, config.template_name,
             config.template_language, hashlib.sha256(config.template_body.encode("utf-8")).hexdigest())
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def load_config() -> WhatsAppConfig:
    if not settings.whatsapp_secret_arn:
        raise WhatsAppConfigurationError("WhatsApp provider secret is not configured")
    try:
        secret = boto3.client(
            "secretsmanager",
            region_name=settings.aws_region or None,
            config=Config(connect_timeout=2, read_timeout=3, retries={"total_max_attempts": 2}),
        ).get_secret_value(SecretId=settings.whatsapp_secret_arn).get("SecretString", "")
        data = json.loads(secret)
        config = WhatsAppConfig(
            access_token=data["access_token"],
            phone_number_id=data["phone_number_id"],
            app_secret=data["app_secret"],
            verify_token=data["verify_token"],
            api_version=data["api_version"],
            template_name=data["template_name"],
            template_language=data["template_language"],
            template_body=data["template_body"],
        )
    except Exception as exc:
        raise WhatsAppConfigurationError("WhatsApp provider configuration is unavailable or malformed") from exc
    if not all(isinstance(value, str) and value.strip() for value in (
        config.access_token, config.app_secret, config.verify_token, config.template_body,
    )):
        raise WhatsAppConfigurationError("WhatsApp provider credentials are incomplete")
    if not isinstance(config.phone_number_id, str) or not isinstance(config.api_version, str):
        raise WhatsAppConfigurationError("WhatsApp provider identifiers are malformed")
    if not isinstance(config.template_name, str) or not isinstance(config.template_language, str):
        raise WhatsAppConfigurationError("WhatsApp template configuration is malformed")
    if not re.fullmatch(r"\d{5,32}", config.phone_number_id):
        raise WhatsAppConfigurationError("WhatsApp phone number ID is malformed")
    if not re.fullmatch(r"v\d{2,3}\.\d", config.api_version):
        raise WhatsAppConfigurationError("WhatsApp Graph API version is malformed")
    if not re.fullmatch(r"[a-z0-9_]{1,512}", config.template_name):
        raise WhatsAppConfigurationError("WhatsApp template name is malformed")
    if not re.fullmatch(r"[a-z]{2,3}(?:_[A-Z]{2})?", config.template_language):
        raise WhatsAppConfigurationError("WhatsApp template language is malformed")
    if (not isinstance(config.template_body, str) or len(config.template_body) > 1024
            or config.template_body.count("{{1}}") != 1
            or re.search(r"\{\{(?!1\})\d+\}\}", config.template_body)):
        raise WhatsAppConfigurationError("WhatsApp template body must have one supported {{1}} parameter and match the pilot-approved text")
    return config


def _provider_error_code(body: bytes) -> Optional[str]:
    try:
        value = json.loads(body).get("error", {}).get("code")
        return str(value)[:32] if value is not None else None
    except (ValueError, AttributeError):
        return None


def send_approved_template(config: WhatsAppConfig, phone_e164: str, approved_draft: str, callback_id: str) -> WhatsAppSendResult:
    """Make one network attempt. Never retry transport or ambiguous provider outcomes."""
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_e164.strip().lstrip("+"),
        "type": "template",
        "template": {
            "name": config.template_name,
            "language": {"code": config.template_language},
            "components": [{"type": "body", "parameters": [{"type": "text", "text": approved_draft}]}],
        },
        "biz_opaque_callback_data": callback_id,
    }
    request = Request(
        f"https://graph.facebook.com/{config.api_version}/{config.phone_number_id}/messages",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {config.access_token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=8) as response:
            body = response.read(64 * 1024)
            parsed = json.loads(body)
        message_id = parsed.get("messages", [{}])[0].get("id")
        if not isinstance(message_id, str) or not message_id or len(message_id) > 256:
            return WhatsAppSendResult("unknown", error_code="invalid_provider_response")
        return WhatsAppSendResult("accepted", provider_message_id=message_id)
    except HTTPError as exc:
        body = exc.read(64 * 1024)
        if 400 <= exc.code < 500:
            return WhatsAppSendResult("failed", error_code=_provider_error_code(body) or f"http_{exc.code}")
        return WhatsAppSendResult("unknown", error_code=f"http_{exc.code}")
    except (URLError, TimeoutError, OSError, ValueError):
        return WhatsAppSendResult("unknown", error_code="transport_or_response_ambiguous")


def verify_webhook_signature(app_secret: str, raw_body: bytes, supplied_signature: str) -> bool:
    if not supplied_signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, supplied_signature)
