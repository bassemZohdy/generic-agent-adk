"""Small local release API described by the OpenAPI toolset."""

from fastapi import FastAPI


app = FastAPI(title="Release Status API", version="0.1.0")


@app.get("/release/status", operation_id="getReleaseStatus")
def get_release_status() -> dict[str, str]:
    """Return the service status used by release-readiness checks."""
    return {
        "service": "basic-adk-agent",
        "environment": "local",
        "status": "healthy",
        "version": "0.1.0",
        "deployment": "docker-compose",
    }
