"""OIDC access-token authentication for the single-customer deployment model."""

from typing import Any, Callable, Dict

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from urllib.parse import urlparse

from app.config.settings import settings

_bearer = HTTPBearer(auto_error=False)
_jwks_clients: dict[str, PyJWKClient] = {}


def require_authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Dict[str, Any]:
    """Require a signed bearer token belonging to this deployment's tenant."""
    if credentials is None and settings.demo_enabled:
        return {"sub": "demo-user", "tenant_id": "demo", "demo": True}
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not all((settings.jwt_issuer, settings.jwt_jwks_url, settings.jwt_audience, settings.jwt_required_scope, settings.tenant_id)):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured for this deployment",
        )

    issuer = settings.jwt_issuer.rstrip("/")
    if urlparse(issuer).scheme != "https" or urlparse(settings.jwt_jwks_url).scheme != "https":
        raise HTTPException(status_code=503, detail="Identity provider URLs must use HTTPS")
    client = _jwks_clients.get(issuer)
    if client is None:
        client = PyJWKClient(settings.jwt_jwks_url, cache_keys=True, timeout=5)
        _jwks_clients[issuer] = client
    try:
        signing_key = client.get_signing_key_from_jwt(credentials.credentials)
        claims = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_aud": False, "require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Bearer token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid bearer token") from exc
    except Exception as exc:
        # JWKS retrieval/signature-key resolution failures are upstream outages,
        # not evidence that the supplied token is invalid.
        raise HTTPException(status_code=503, detail="Identity provider unavailable") from exc

    token_audiences = claims.get("aud", [])
    if isinstance(token_audiences, str):
        token_audiences = [token_audiences]
    elif not isinstance(token_audiences, list):
        raise HTTPException(status_code=401, detail="Token audience is invalid")
    if token_audiences:
        audience_matches = settings.jwt_audience in token_audiences
    else:
        # Some providers (including Cognito access tokens) omit `aud` and use
        # `client_id`; accept that form only when no resource audience is set.
        audience_matches = claims.get("client_id") == settings.jwt_audience
    if not audience_matches:
        raise HTTPException(status_code=401, detail="Token was issued to another client")

    if claims.get("token_use") not in (None, "access"):
        raise HTTPException(status_code=401, detail="An access token is required")
    token_scopes = claims.get("scope", claims.get("scp", []))
    if isinstance(token_scopes, str):
        token_scopes = token_scopes.split()
    if settings.jwt_required_scope not in token_scopes:
        raise HTTPException(status_code=403, detail="Token lacks the required API scope")

    token_tenant = claims.get("custom:tenant_id", claims.get("tenant_id"))
    if token_tenant != settings.tenant_id:
        raise HTTPException(status_code=403, detail="Token does not belong to this company")
    if not claims.get("sub"):
        raise HTTPException(status_code=401, detail="Token subject is missing")
    return claims


def require_roles(*allowed_roles: str) -> Callable[..., Dict[str, Any]]:
    """Create a route dependency that enforces one of the configured roles."""
    def check_role(user: Dict[str, Any] = Depends(require_authenticated_user)) -> Dict[str, Any]:
        if user.get("demo"):
            return user
        roles = user.get("roles", user.get("cognito:groups", []))
        if isinstance(roles, str):
            roles = [roles]
        if not set(allowed_roles).intersection(roles):
            raise HTTPException(status_code=403, detail="Insufficient role for this action")
        return user

    return check_role
