"""Generic service-status API described by the configured OpenAPI toolset."""

from fastapi import FastAPI, Header, HTTPException, Request

from .auth import authenticate_request
from .config import settings


app = FastAPI(title=settings.openapi_title, version=settings.app_version)


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
    authenticate_request(
        request, api_key=x_api_key, required_roles=settings.service_api_roles
    )
    if settings.service_api_key and x_api_key != settings.service_api_key and not request.headers.get("authorization"):
        raise HTTPException(status_code=401, detail="Invalid service API key")
    return get_service_status()
