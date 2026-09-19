"""
LeadRescue AI — FastAPI Application Entry Point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from app.api.router import api_router

app = FastAPI(
    title="LeadRescue AI",
    description="AI-powered lead rescue system for SMBs",
    version="0.2.0",
)

# CORS middleware for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Router
app.include_router(api_router)


@app.get("/health")
async def health_check():
    """Health check endpoint to verify the application is running."""
    return {
        "status": "healthy",
        "service": "leadrescue-ai",
        "phase": "backend_foundation",
    }


# Lambda handler via Mangum
handler = Mangum(app, lifespan="off")
