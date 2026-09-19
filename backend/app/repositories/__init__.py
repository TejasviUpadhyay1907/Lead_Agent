"""
LeadRescue AI — Repositories Package Initialization
Exposes LeadsRepository, FollowUpsRepository, AuditRepository, ConfigRepository.
"""

from app.repositories.audit import AuditRepository
from app.repositories.config import ConfigRepository
from app.repositories.followups import FollowUpsRepository
from app.repositories.leads import LeadsRepository

__all__ = [
    "LeadsRepository",
    "FollowUpsRepository",
    "AuditRepository",
    "ConfigRepository",
]
