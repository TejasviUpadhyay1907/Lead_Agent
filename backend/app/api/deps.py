"""
LeadRescue AI — API Dependency Injection
Provides repository singleton instances for FastAPI endpoints.
"""

from app.repositories.audit import AuditRepository
from app.repositories.config import ConfigRepository
from app.repositories.followups import FollowUpsRepository
from app.repositories.leads import LeadsRepository

# Singleton repository instances
_leads_repo = LeadsRepository()
_followups_repo = FollowUpsRepository()
_audit_repo = AuditRepository()
_config_repo = ConfigRepository()


def get_leads_repo() -> LeadsRepository:
    return _leads_repo


def get_followups_repo() -> FollowUpsRepository:
    return _followups_repo


def get_audit_repo() -> AuditRepository:
    return _audit_repo


def get_config_repo() -> ConfigRepository:
    return _config_repo
