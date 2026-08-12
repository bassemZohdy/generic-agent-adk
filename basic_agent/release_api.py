"""Small local release API described by the OpenAPI toolset."""

from fastapi import FastAPI, Header, HTTPException, Request

from .auth import authenticate_request
from .config import settings


app = FastAPI(title="Release Status API", version=settings.app_version)


def get_release_status() -> dict[str, str]:
    """Return the service status payload used by release-readiness checks."""
    return {
        "service": "basic-adk-agent",
        "environment": "local",
        "status": "healthy",
        "version": settings.app_version,
        "deployment": settings.deployment,
    }


@app.get("/release/status", operation_id="getReleaseStatus")
def release_status(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> dict[str, str]:
    """Return status after Keycloak or internal API-key authentication."""
    authenticate_request(
        request, api_key=x_api_key, required_roles=settings.release_api_roles
    )
    expected_key = settings.release_api_key
    if expected_key and x_api_key != expected_key and not request.headers.get("authorization"):
        raise HTTPException(status_code=401, detail="Invalid release API key")
    return get_release_status()
