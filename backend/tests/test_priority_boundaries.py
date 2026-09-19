"""
LeadRescue AI — Priority Classification Boundary Tests
Verifies exact boundaries:
0 -> COLD
49 -> COLD
50 -> WARM
79 -> WARM
80 -> HOT
100 -> HOT
"""

from app.models.enums import PriorityEnum
from app.policy.priority import classify_priority


def test_priority_exact_boundaries():
    assert classify_priority(0) == PriorityEnum.COLD
    assert classify_priority(49) == PriorityEnum.COLD
    assert classify_priority(50) == PriorityEnum.WARM
    assert classify_priority(79) == PriorityEnum.WARM
    assert classify_priority(80) == PriorityEnum.HOT
    assert classify_priority(100) == PriorityEnum.HOT
