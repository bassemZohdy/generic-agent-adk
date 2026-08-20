"""Traefik ForwardAuth endpoint backed by Keycloak JWT validation."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import Response

from ..config.settings import settings
from ..util import is_production
from .core import authenticate_request, keycloak_enabled

_production = is_production(settings.deployment)
app = FastAPI(
    title="Keycloak ForwardAuth",
    version=settings.app_version,
    docs_url=None if _production else "/docs",
    redoc_url=None if _production else "/redoc",
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "provider": "keycloak"}


@app.get("/verify")
def verify(request: Request) -> Response:
    """Return 2xx only for a valid Keycloak bearer token."""
    if not keycloak_enabled() and not settings.auth_disabled:
        return Response(
            status_code=503, content="Keycloak authentication is not configured"
        )
    claims = authenticate_request(
        request, required_roles=settings.keycloak_required_roles
    )
    response = Response(status_code=200)
    if claims and (subject := claims.get("sub")):
        response.headers["X-Auth-User"] = str(subject)
    return response
