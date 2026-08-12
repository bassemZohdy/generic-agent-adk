"""Keycloak OIDC bearer-token validation for the application APIs."""

from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException, Request, WebSocket
from jwt import PyJWKClient
import jwt


def _setting(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    return value.strip() if value and value.strip() else None


def keycloak_enabled() -> bool:
    return bool(_setting("KEYCLOAK_ISSUER"))


def _decode(token: str) -> dict[str, Any]:
    issuer = _setting("KEYCLOAK_ISSUER")
    if not issuer:
        raise HTTPException(status_code=503, detail="Keycloak authentication is not configured")
    jwks_url = _setting(
        "KEYCLOAK_JWKS_URL",
        f"{issuer.rstrip('/')}/protocol/openid-connect/certs",
    )
    try:
        signing_key = PyJWKClient(jwks_url).get_signing_key_from_jwt(token)
        audience = _setting("KEYCLOAK_AUDIENCE")
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


def authenticate_request(request: Request, *, api_key: str | None = None) -> dict[str, Any] | None:
    """Authenticate bearer tokens, retaining the internal API-key escape hatch."""
    if not keycloak_enabled():
        return None
    token = token_from_request(request)
    if token:
        return _decode(token)
    expected_key = _setting("RELEASE_API_KEY")
    if expected_key and api_key == expected_key:
        return {"sub": "internal-service", "auth_method": "api_key"}
    raise HTTPException(status_code=401, detail="Bearer token required")


def authenticate_websocket(websocket: WebSocket) -> dict[str, Any] | None:
    """Authenticate a WebSocket using a bearer header or query token."""
    if not keycloak_enabled():
        return None
    header = websocket.headers.get("authorization", "")
    _, _, token = header.partition(" ")
    if not header.lower().startswith("bearer "):
        token = websocket.query_params.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Bearer token required")
    return _decode(token)
