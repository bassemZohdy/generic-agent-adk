"""Generic service-status API described by the configured OpenAPI toolset."""

import logging

from fastapi import FastAPI, Header, Request

from .auth import authenticate_request, roles_from_claims
from .config import settings


logger = logging.getLogger(__name__)
_production = settings.deployment.lower() in {"prod", "production", "staging", "cloud-run", "cloudrun"}
app = FastAPI(
    title=settings.openapi_title,
    version=settings.app_version,
    docs_url=None if _production else "/docs",
    redoc_url=None if _production else "/redoc",
)


def get_service_status() -> dict[str, str]:
    """Return a generic status payload for the configured agent environment."""
    return {
        "service": settings.app_name,
        "environment": settings.deployment,
        "status": "healthy",
        "version": settings.app_version,
    }


@app.get("/status", operation_id="getServiceStatus")
@app.get("/release/status", include_in_schema=False)
def service_status(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> dict[str, str]:
    """Return status after Keycloak or internal service-key authentication."""
    claims = authenticate_request(
        request, api_key=x_api_key, required_roles=settings.service_api_roles
    )
    logger.info(
        "authenticated service request sub=%s auth_method=%s roles=%s path=%s",
        claims.get("sub") if claims else "auth-disabled",
        claims.get("auth_method", "bearer") if claims else "disabled",
        sorted(roles_from_claims(claims)) if claims else [],
        request.url.path,
    )
    return get_service_status()
