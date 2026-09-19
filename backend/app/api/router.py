"""
LeadRescue AI — Main API Router
Aggregates all route modules under the /api prefix.
"""

from fastapi import APIRouter

from app.api.audit import router as audit_router
from app.api.config import router as config_router
from app.api.followups import router as followups_router
from app.api.leads import router as leads_router

api_router = APIRouter(prefix="/api")

api_router.include_router(leads_router)
api_router.include_router(followups_router)
api_router.include_router(audit_router)
api_router.include_router(config_router)
