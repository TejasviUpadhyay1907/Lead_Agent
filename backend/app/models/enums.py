"""
LeadRescue AI — Controlled State Enums
Strict enums according to Phase 0 Revision 3 architecture.
"""

from enum import Enum


class SourceEnum(str, Enum):
    WEBSITE = "website"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    INSTAGRAM = "instagram"
    MARKETPLACE = "marketplace"
    PHONE = "phone"
    MANUAL = "manual"


class IntentEnum(str, Enum):
    PURCHASE = "purchase"
    INQUIRY = "inquiry"
    SUPPORT = "support"
    OTHER = "other"


class UrgencyEnum(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PriorityEnum(str, Enum):
    HOT = "HOT"
    WARM = "WARM"
    COLD = "COLD"


class LifecycleStatusEnum(str, Enum):
    NEW = "new"
    ANALYZED = "analyzed"
    CONTACTED = "contacted"
    FOLLOW_UP = "follow_up"
    RESOLVED = "resolved"
    OPTED_OUT = "opted_out"


class RiskStatusEnum(str, Enum):
    NORMAL = "normal"
    AT_RISK = "at_risk"


class ResponseStatusEnum(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    SENT = "sent"
    # Kept for records written by earlier versions. This never proves delivery.
    SIMULATED_SENT = "simulated_sent"
    REJECTED = "rejected"


class SalesOutcomeEnum(str, Enum):
    """Operator-recorded business outcome; never inferred by the agent."""
    WON = "won"
    LOST = "lost"
    DISQUALIFIED = "disqualified"


class FollowUpStatusEnum(str, Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class CustomerStageEnum(str, Enum):
    NEW = "new"
    RETURNING = "returning"
