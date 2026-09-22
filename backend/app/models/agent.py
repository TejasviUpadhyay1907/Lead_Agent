"""
LeadRescue AI — Agent Contract Model
Pydantic schema for validating output from Strands Agent.

CRITICAL ARCHITECTURE BOUNDARY:
- extra = "forbid" rejects any unauthorized fields (e.g. score, priority, risk_status, mutations).
- The agent ONLY understands, extracts, summarizes, recommends, and drafts.
- Software deterministically scores, classifies, risks, and manages persistence.
"""

from typing import Annotated, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CustomerStageEnum, IntentEnum, UrgencyEnum


class AgentAnalysisResult(BaseModel):
    """
    Structured extraction contract for Strands Agent responses.
    Strictly forbids any score, priority, or database mutation fields.
    """
    intent: IntentEnum
    urgency: UrgencyEnum
    product: Optional[str] = Field(default=None, max_length=200)
    quantity: Optional[int] = Field(default=None, ge=0)
    location: Optional[str] = Field(default=None, max_length=200)
    customer_stage: CustomerStageEnum = CustomerStageEnum.NEW
    key_entities: List[Annotated[str, Field(max_length=128)]] = Field(default_factory=list, max_length=20)
    summary: str = Field(..., min_length=1, max_length=2000)
    recommended_action: str = Field(..., min_length=1, max_length=1000)
    response_draft: str = Field(..., min_length=1, max_length=4000)

    # Strictly forbid extra fields (such as score, priority, risk_status, etc.)
    model_config = ConfigDict(extra="forbid")
