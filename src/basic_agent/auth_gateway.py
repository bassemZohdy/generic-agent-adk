"""Traefik ForwardAuth endpoint backed by Keycloak JWT validation."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import Response

from .auth import authenticate_request, keycloak_enabled
from .config import settings


app = FastAPI(title="Keycloak ForwardAuth", version=settings.app_version)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "provider": "keycloak"}


@app.get("/verify")
def verify(request: Request) -> Response:
    """Return 2xx only for a valid Keycloak bearer token."""
    if not keycloak_enabled():
        return Response(status_code=503, content="Keycloak authentication is not configured")
    claims = authenticate_request(
        request, required_roles=settings.keycloak_required_roles
    )
    response = Response(status_code=200)
    if claims:
        if subject := claims.get("sub"):
            response.headers["X-Auth-User"] = str(subject)
        if email := claims.get("email"):
            response.headers["X-Auth-Email"] = str(email)
    return response
