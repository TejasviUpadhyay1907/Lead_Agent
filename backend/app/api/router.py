"""
LeadRescue AI — Main API Router
Aggregates all route modules under the /api prefix.
"""

from fastapi import APIRouter, Depends
from app.api.security import require_authenticated_user
from app.utils.time import effective_now_iso

from app.api.audit import router as audit_router
from app.api.config import router as config_router
from app.api.demo import router as demo_router
from app.api.followups import router as followups_router
from app.api.leads import router as leads_router
from app.api.privacy import router as privacy_router
from app.api.reports import router as reports_router
from app.api.whatsapp import router as whatsapp_router

api_router = APIRouter(prefix="/api", dependencies=[Depends(require_authenticated_user)])


@api_router.get("/server-time", tags=["System"])
def get_server_time():
    """Return authoritative UTC time for deadline and SLA displays."""
    return {"effective_now": effective_now_iso()}

api_router.include_router(leads_router)
api_router.include_router(followups_router)
api_router.include_router(audit_router)
api_router.include_router(config_router)
api_router.include_router(demo_router)
api_router.include_router(privacy_router)
api_router.include_router(reports_router)
api_router.include_router(whatsapp_router)
