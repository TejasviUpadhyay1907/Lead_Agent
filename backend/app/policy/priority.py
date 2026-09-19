"""
LeadRescue AI — Priority Classifier
Deterministically maps score to HOT / WARM / COLD priority enum.
"""

from app.models.enums import PriorityEnum


def classify_priority(score: int) -> PriorityEnum:
    """
    Classify score into priority level:
    80–100 -> HOT
    50–79  -> WARM
    0–49   -> COLD
    """
    if score >= 80:
        return PriorityEnum.HOT
    elif score >= 50:
        return PriorityEnum.WARM
    else:
        return PriorityEnum.COLD
