"""Local MCP server exposing project and release operations data."""

import json

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("basic-project")


@mcp.tool()
def get_release_status() -> str:
    """Return the current service status used by release-readiness checks."""
    return json.dumps(
        {
            "service": "basic-adk-agent",
            "environment": "local",
            "status": "healthy",
            "version": "0.1.0",
            "deployment": "docker-compose",
        }
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
