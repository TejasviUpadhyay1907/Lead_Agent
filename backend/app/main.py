"""
LeadRescue AI — FastAPI Application Entry Point
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from starlette.responses import JSONResponse

from app.api.router import api_router
from app.api.webhooks import router as webhooks_router
from app.api.whatsapp_webhooks import router as whatsapp_webhooks_router
from app.api.deps import get_leads_repo
from app.config.settings import settings
from app.repositories.leads import (
    SuppressionMigrationIncompleteError,
    SuppressionRegistryUnavailableError,
)
from app.repositories.customer_index import CustomerIndexKeyUnavailableError

app = FastAPI(
    title="LeadRescue AI",
    description="AI-powered lead rescue system for SMBs",
    version="0.2.0",
)


@app.exception_handler(SuppressionMigrationIncompleteError)
async def suppression_migration_incomplete(_request: Request, _exc: SuppressionMigrationIncompleteError):
    return JSONResponse(
        status_code=503,
        content={"detail": "Customer opt-out data is being migrated. Retry after the company administrator completes the rollout."},
        headers={"Retry-After": "300"},
    )


@app.exception_handler(SuppressionRegistryUnavailableError)
async def suppression_registry_unavailable(_request: Request, _exc: SuppressionRegistryUnavailableError):
    return JSONResponse(
        status_code=503,
        content={"detail": "Customer opt-out status is temporarily unavailable. Retry shortly."},
        headers={"Retry-After": "30"},
    )


@app.exception_handler(CustomerIndexKeyUnavailableError)
async def customer_index_key_unavailable(_request: Request, _exc: CustomerIndexKeyUnavailableError):
    return JSONResponse(
        status_code=503,
        content={"detail": "Customer identity lookup is temporarily unavailable. Retry shortly."},
        headers={"Retry-After": "30"},
    )

# CORS must be explicitly configured for a deployed frontend. Local development
# uses Vite's same-origin proxy and does not need cross-origin access.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Next-Cursor"],
)

# Include API Router
app.include_router(api_router)
app.include_router(webhooks_router)
app.include_router(whatsapp_webhooks_router)


@app.get("/health")
def health_check():
    """Liveness check for the application process."""
    return {
        "status": "healthy",
        "service": "leadrescue-ai",
    }


@app.get("/ready")
def readiness_check():
    """Readiness requires completed opt-out migration and an available HMAC key."""
    get_leads_repo().suppression_registry_ready()
    return {"status": "ready"}


# Lambda handler via Mangum
handler = Mangum(app, lifespan="off")
