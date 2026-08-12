"""Local MCP server exposing generic configured service data."""

import json

from mcp.server.fastmcp import FastMCP

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
