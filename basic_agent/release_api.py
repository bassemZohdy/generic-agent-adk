"""Small local release API described by the OpenAPI toolset."""

import os

from fastapi import FastAPI, Header, HTTPException, Request

from .auth import authenticate_request


app = FastAPI(title="Release Status API", version="0.1.0")


def get_release_status() -> dict[str, str]:
    """Return the service status payload used by release-readiness checks."""
    return {
        "service": "basic-adk-agent",
        "environment": "local",
        "status": "healthy",
        "version": "0.1.0",
        "deployment": "docker-compose",
    }


@app.get("/release/status", operation_id="getReleaseStatus")
def release_status(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> dict[str, str]:
    """Return status after Keycloak or internal API-key authentication."""
    authenticate_request(request, api_key=x_api_key)
    expected_key = os.getenv("RELEASE_API_KEY")
    if expected_key and x_api_key != expected_key and not request.headers.get("authorization"):
        raise HTTPException(status_code=401, detail="Invalid release API key")
    return get_release_status()
