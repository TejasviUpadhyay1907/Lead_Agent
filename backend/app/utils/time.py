"""
LeadRescue AI — Centralized Time Abstraction
Provides effective_now() supporting system UTC time normally and simulated demo clock.
"""

from datetime import datetime, timezone
from typing import Optional

_simulated_time: Optional[datetime] = None


def effective_now() -> datetime:
    """
    Returns current effective time in UTC.
    If a simulated time is set (for demo mode / testing), returns simulated time.
    """
    if _simulated_time is not None:
        return _simulated_time
    return datetime.now(timezone.utc)


def effective_now_iso() -> str:
    """Returns ISO 8601 formatted effective now string in UTC."""
    return effective_now().isoformat()


def set_simulated_now(dt: datetime) -> None:
    """Set a simulated effective clock time (used for demo mode and time-advance testing)."""
    global _simulated_time
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    _simulated_time = dt


def reset_simulated_now() -> None:
    """Reset clock back to system UTC time."""
    global _simulated_time
    _simulated_time = None
