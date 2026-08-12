"""Small local MCP server used by the ADK MCP integration example."""

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("basic-project")


@mcp.tool()
def get_project_status() -> str:
    """Return the current status exposed by this project's MCP server."""
    return "The basic ADK project is running with local MCP integration enabled."


if __name__ == "__main__":
    mcp.run(transport="stdio")
