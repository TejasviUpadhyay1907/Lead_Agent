"""
LeadRescue AI — Application Configuration

Uses pydantic-settings to load configuration from environment variables.
Secrets are never committed to source control.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # AWS
    aws_region: str = ""
    bedrock_model_id: str = ""

    # DynamoDB table names
    leads_table: str = "leadrescue-leads"
    followups_table: str = "leadrescue-followups"
    audit_table: str = "leadrescue-audit"
    config_table: str = "leadrescue-config"
    processed_events_table: str = "leadrescue-processed-events"
    customer_suppressions_table: str = "leadrescue-customer-suppressions"
    analysis_jobs_table: str = "leadrescue-analysis-jobs"
    privacy_requests_table: str = "leadrescue-privacy-requests"
    analysis_queue_url: str = ""
    analysis_dlq_arn: str = ""
    webhook_secret_arn: str = ""
    zoho_webhook_secret_arn: str = ""
    whatsapp_secret_arn: str = ""
    whatsapp_outbound_enabled: bool = False
    whatsapp_messages_table: str = "leadrescue-whatsapp-messages"
    customer_index_secret_arn: str = ""

    # Application mode
    # Development defaults to synthetic mode; the SAM production template sets false.
    demo_mode: bool = True
    app_env: str = "local"
    cors_origins: str = ""
    jwt_issuer: str = ""
    jwt_jwks_url: str = ""
    jwt_audience: str = ""
    jwt_required_scope: str = ""
    tenant_id: str = ""
    admin_role: str = "company_admin"
    operator_role: str = "sales_operator"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def effective_tenant_id(self) -> str:
        return self.tenant_id or ("demo" if self.demo_enabled else "")

    @property
    def demo_enabled(self) -> bool:
        return self.demo_mode and self.app_env.lower() in {"local", "test"}


# Singleton settings instance
settings = Settings()
