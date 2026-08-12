"""Keycloak OIDC bearer-token validation for the application APIs."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, WebSocket
from jwt import PyJWKClient
import jwt

from .config import settings


def keycloak_enabled() -> bool:
    return bool(settings.keycloak_issuer)


def _decode(token: str) -> dict[str, Any]:
    issuer = settings.keycloak_issuer
    if not issuer:
        raise HTTPException(status_code=503, detail="Keycloak authentication is not configured")
    jwks_url = settings.keycloak_jwks_url
    try:
        signing_key = PyJWKClient(jwks_url).get_signing_key_from_jwt(token)
        audience = settings.keycloak_audience or None
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=audience,
            options={"verify_aud": bool(audience)},
        )
    except (jwt.PyJWTError, ValueError, OSError) as error:
        raise HTTPException(status_code=401, detail="Invalid Keycloak access token") from error


def token_from_request(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    return token if scheme.lower() == "bearer" and token else None


def _claim_roles(claims: dict[str, Any]) -> set[str]:
    value: Any = claims
    for part in settings.keycloak_role_claim.split("."):
        value = value.get(part, {}) if isinstance(value, dict) else {}
    return set(value if isinstance(value, list) else [])


def require_roles(claims: dict[str, Any], required_roles: tuple[str, ...]) -> None:
    if required_roles and not set(required_roles).intersection(_claim_roles(claims)):
        raise HTTPException(status_code=403, detail="Required Keycloak role is missing")


def authenticate_request(
    request: Request,
    *,
    api_key: str | None = None,
    required_roles: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    """Authenticate bearer tokens, retaining the internal API-key escape hatch."""
    if not keycloak_enabled():
        return None
    token = token_from_request(request)
    if token:
        claims = _decode(token)
        require_roles(claims, required_roles)
        return claims
    if settings.release_api_key and api_key == settings.release_api_key:
        return {"sub": "internal-service", "auth_method": "api_key"}
    raise HTTPException(status_code=401, detail="Bearer token required")


def authenticate_websocket(
    websocket: WebSocket,
    *,
    required_roles: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    """Authenticate a WebSocket using a bearer header or query token."""
    if not keycloak_enabled():
        return None
    header = websocket.headers.get("authorization", "")
    _, _, token = header.partition(" ")
    if not header.lower().startswith("bearer "):
        token = websocket.query_params.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Bearer token required")
    claims = _decode(token)
    require_roles(claims, required_roles)
    return claims
