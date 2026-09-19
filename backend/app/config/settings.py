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

    # Application mode
    demo_mode: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Singleton settings instance
settings = Settings()
