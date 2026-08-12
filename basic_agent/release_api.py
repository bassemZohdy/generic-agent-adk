"""Small local release API described by the OpenAPI toolset."""

import os

from fastapi import FastAPI, Header, HTTPException


app = FastAPI(title="Release Status API", version="0.1.0")


@app.get("/release/status", operation_id="getReleaseStatus")
def get_release_status(x_api_key: str | None = Header(default=None)) -> dict[str, str]:
    """Return the service status used by release-readiness checks."""
    expected_key = os.getenv("RELEASE_API_KEY")
    if expected_key and x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid release API key")
    return {
        "service": "basic-adk-agent",
        "environment": "local",
        "status": "healthy",
        "version": "0.1.0",
        "deployment": "docker-compose",
    }
