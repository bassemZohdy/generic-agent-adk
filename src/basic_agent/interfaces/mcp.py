"""Local MCP server exposing generic configured service data."""

import json

from mcp.server.fastmcp import FastMCP

try:  # Package import for tests; absolute fallback when launched by MCP over stdio.
    from ..config.settings import settings
except ImportError:  # pragma: no cover - exercised by ``python mcp_server.py``
    from basic_agent.config import settings


mcp = FastMCP("basic-project")


@mcp.tool()
def get_service_status() -> str:
    """Return the current status of the configured application service."""
    return json.dumps(
        {
            "service": "basic-adk-agent",
            "environment": "local",
            "status": "healthy",
            "version": settings.app_version,
            "deployment": settings.deployment,
        }
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
