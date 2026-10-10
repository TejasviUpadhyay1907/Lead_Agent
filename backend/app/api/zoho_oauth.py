"""Public callback endpoint for the admin-started Zoho OAuth flow."""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.integrations.zoho_oauth import (
    ZohoOAuthError,
    connect_with_authorization_code,
    mark_authorization_denied,
)

public_router = APIRouter(prefix="/integrations/v1/zoho/oauth", tags=["Integrations"])


@public_router.get("/callback")
def zoho_oauth_callback(
    state: str = Query(min_length=32, max_length=256),
    code: str | None = Query(default=None, max_length=4096),
    error: str | None = Query(default=None, max_length=128),
):
    """Consume Zoho's grant once and persist only its refresh token in Secrets Manager."""
    headers = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
    if error is not None:
        try:
            mark_authorization_denied(state)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=headers)
        return JSONResponse(
            content={"connected": False, "detail": "Zoho authorization was declined. You may close this window."},
            headers=headers,
        )
    if not code:
        return JSONResponse(status_code=400, content={"detail": "Zoho authorization response is incomplete"}, headers=headers)
    try:
        connect_with_authorization_code(state, code)
    except ZohoOAuthError as exc:
        return JSONResponse(status_code=502, content={"detail": "Zoho authorization could not be completed"}, headers=headers)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=headers)
    return JSONResponse(
        content={"connected": True, "detail": "Zoho CRM connection completed. You may close this window."},
        headers=headers,
    )
